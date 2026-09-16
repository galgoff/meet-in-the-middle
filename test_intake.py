"""
test_intake.py — Week 2: multi-party intake, state, PII guardrails, and
input validation.

Most of these are pure SQLite + regex — no network, so unlike
test_tools.py's geocoding tests, none of these should ever be flaky.
Each test gets its own throwaway db file via the `db_path` fixture so
tests can't interfere with each other or with a real trip.db. The
_classify_*_input tests mock intake.geocode_city or check against the
real (in-memory, no-network) countries.py list directly.
"""

import sqlite3
from unittest.mock import patch

import pytest

import intake
from db import TripError, add_submission, create_trip, get_trip, init_db, lock_trip
from guardrails import scrub_passport_like


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_trip.db")


def _submit(trip_id, db_path, name, city="Lisbon", **kwargs):
    return add_submission(trip_id, person_name=name, origin_city=city, db_path=db_path, **kwargs)


def test_trip_starts_open_and_completes_at_expected_count(db_path):
    trip_id = create_trip(3, db_path=db_path)
    assert get_trip(trip_id, db_path=db_path)["status"] == "open"

    _submit(trip_id, db_path, "Alice")
    _submit(trip_id, db_path, "Bob")
    assert get_trip(trip_id, db_path=db_path)["status"] == "open"

    result = _submit(trip_id, db_path, "Carol")
    assert result["status"] == "complete"
    assert result["locked_early"] == 0


def test_submission_rejected_once_trip_is_complete(db_path):
    trip_id = create_trip(2, db_path=db_path)
    _submit(trip_id, db_path, "Alice")
    _submit(trip_id, db_path, "Bob")

    with pytest.raises(TripError):
        _submit(trip_id, db_path, "Dave")  # a late arrival must not reshuffle the group


def test_resubmitting_before_completion_updates_in_place(db_path):
    trip_id = create_trip(3, db_path=db_path)
    _submit(trip_id, db_path, "Alice", city="Lisbon")
    _submit(trip_id, db_path, "Alice", city="Porto")  # changed her mind, still 1 person

    trip = get_trip(trip_id, db_path=db_path)
    assert trip["status"] == "open"  # still only 1 distinct person submitted


def test_manual_lock_completes_trip_early_and_blocks_further_submissions(db_path):
    trip_id = create_trip(5, db_path=db_path)  # expects 5, only 2 will ever show up
    _submit(trip_id, db_path, "Alice")
    _submit(trip_id, db_path, "Bob")

    result = lock_trip(trip_id, db_path=db_path)
    assert result["status"] == "complete"
    assert result["locked_early"] == 1

    with pytest.raises(TripError):
        _submit(trip_id, db_path, "Carol")  # the non-responder can't jump back in either


def test_lock_requires_at_least_two_submissions(db_path):
    trip_id = create_trip(4, db_path=db_path)
    _submit(trip_id, db_path, "Alice")

    with pytest.raises(TripError):
        lock_trip(trip_id, db_path=db_path)


def test_lock_on_already_complete_trip_is_rejected(db_path):
    trip_id = create_trip(2, db_path=db_path)
    _submit(trip_id, db_path, "Alice")
    _submit(trip_id, db_path, "Bob")

    with pytest.raises(TripError):
        lock_trip(trip_id, db_path=db_path)


def test_create_trip_requires_at_least_two_expected_parties(db_path):
    with pytest.raises(TripError):
        create_trip(1, db_path=db_path)


def test_no_passport_number_column_exists_in_schema(db_path):
    """Structural guardrail: the field simply doesn't exist to leak."""
    import sqlite3

    create_trip(2, db_path=db_path)  # ensures the db + schema exist
    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(submissions)")}
    conn.close()
    assert not any("passport" in c.lower() for c in columns)
    assert "nationality" in columns


def test_guardrail_redacts_passport_like_text_in_free_text_fields(db_path):
    trip_id = create_trip(2, db_path=db_path)
    result = _submit(
        trip_id, db_path, "Alice",
        hard_constraints="my passport is X1234567, please don't lose it",
    )
    assert result["redacted"] is True

    submissions = _submissions_for(trip_id, db_path)
    stored = [s for s in submissions if s["person_name"] == "Alice"][0]
    assert "X1234567" not in stored["hard_constraints"]
    assert "redacted" in stored["hard_constraints"].lower()


def test_guardrail_covers_nationality_field_too(db_path):
    """Nationality is exactly the field someone might paste a passport
    number into by mistake instead of a country name — this must be
    scrubbed too, not just hard_constraints/date_flexibility."""
    trip_id = create_trip(2, db_path=db_path)
    result = _submit(trip_id, db_path, "Bob", nationality="my passport is X1234567")
    assert result["redacted"] is True

    stored = [s for s in _submissions_for(trip_id, db_path) if s["person_name"] == "Bob"][0]
    assert "X1234567" not in stored["nationality"]


def test_guardrail_leaves_ordinary_text_alone(db_path):
    clean, redacted = scrub_passport_like("no red-eyes please, traveling with a toddler")
    assert redacted is False
    assert clean == "no red-eyes please, traveling with a toddler"


def _submissions_for(trip_id, db_path):
    from db import get_submissions
    return get_submissions(trip_id, db_path=db_path)


def test_travel_preference_stored_and_normalized(db_path):
    trip_id = create_trip(2, db_path=db_path)
    _submit(trip_id, db_path, "Alice", travel_preference="Ground")
    _submit(trip_id, db_path, "Bob")  # no preference given

    subs = {s["person_name"]: s for s in _submissions_for(trip_id, db_path)}
    assert subs["Alice"]["travel_preference"] == "prefer_ground"
    assert subs["Bob"]["travel_preference"] == "no_preference"


def test_old_db_without_travel_preference_column_gets_migrated(db_path):
    """A trip.db from before this field existed shouldn't need to be
    thrown away — init_db() (called via create_trip) should add the
    column in place."""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE trips (
            id TEXT PRIMARY KEY, expected_parties INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'open', locked_early INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL, completed_at REAL
        );
        CREATE TABLE submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id TEXT NOT NULL REFERENCES trips(id),
            person_name TEXT NOT NULL, origin_city TEXT NOT NULL, date_flexibility TEXT,
            budget_ceiling_usd REAL, nationality TEXT, hard_constraints TEXT,
            submitted_at REAL NOT NULL, UNIQUE(trip_id, person_name)
        );
    """)
    conn.commit()
    conn.close()

    init_db(db_path)
    columns = {row[1] for row in sqlite3.connect(db_path).execute("PRAGMA table_info(submissions)")}
    assert "travel_preference" in columns

    trip_id = create_trip(2, db_path=db_path)
    _submit(trip_id, db_path, "Carol", travel_preference="speed")
    stored = _submissions_for(trip_id, db_path)[0]
    assert stored["travel_preference"] == "prefer_speed"


# --- input validation: origin city ---

def test_classify_city_input_ok_for_a_clean_match():
    fake_geo = {
        "city": "Lisbon", "lat": 38.7, "lon": -9.1,
        "country": "Portugal", "display_name": "Lisbon, Portugal",
    }
    with patch("intake.geocode_city", return_value=fake_geo):
        status, message = intake._classify_city_input("Lisbon, Portugal")
    assert status == "ok"
    assert "Lisbon" in message


def test_classify_city_input_flags_an_unresolvable_typo():
    """The exact case that started this: 'Londom, England' should be
    flagged now, at submit time, not silently stored and only
    discovered when midpoint_agent.py runs — possibly after the trip
    is already locked."""
    fake_geo = {"error": "No match found for 'Londom, England'."}
    with patch("intake.geocode_city", return_value=fake_geo):
        status, message = intake._classify_city_input("Londom, England")
    assert status == "error"
    assert "No match found" in message


def test_classify_city_input_accepts_ambiguous_with_a_warning():
    fake_geo = {
        "city": "Springfield", "lat": 1.0, "lon": 2.0, "country": "United States",
        "display_name": "Springfield, Illinois, United States", "ambiguous": True,
        "alternatives": [{"display_name": "Springfield, Missouri, United States"}],
    }
    with patch("intake.geocode_city", return_value=fake_geo):
        status, message = intake._classify_city_input("Springfield")
    assert status == "ambiguous"
    assert "Missouri" in message


# --- input validation: budget ---

def test_classify_budget_input_blank_is_ok_and_unset():
    status, value, _ = intake._classify_budget_input("")
    assert status == "ok"
    assert value is None


def test_classify_budget_input_rejects_non_numeric_text():
    status, value, message = intake._classify_budget_input("lots")
    assert status == "invalid"
    assert value is None
    assert "number" in message


def test_classify_budget_input_rejects_zero_and_negative_values():
    for raw in ("0", "-50"):
        status, value, _ = intake._classify_budget_input(raw)
        assert status == "invalid"
        assert value is None


def test_classify_budget_input_accepts_a_positive_number():
    status, value, _ = intake._classify_budget_input("1200")
    assert status == "ok"
    assert value == 1200.0


# --- input validation: nationality ---

def test_classify_nationality_input_accepts_a_known_country():
    status, result = intake._classify_nationality_input("portugal")
    assert status == "ok"
    assert result == "Portugal"


def test_classify_nationality_input_accepts_a_common_alias():
    status, result = intake._classify_nationality_input("USA")
    assert status == "ok"
    assert result == "United States"


def test_classify_nationality_input_rejects_gibberish():
    """The exact case that started this: 'Googoo' is not a country and
    must be rejected, not silently stored."""
    status, result = intake._classify_nationality_input("Googoo")
    assert status == "error"
    assert "Googoo" in result


# --- input validation: ambiguous-city confirmation ---

def test_accepts_ambiguous_match_requires_explicit_yes():
    """The exact case that started this: 'London, en' resolved
    ambiguously to Svalbard, Norway and was silently accepted. Only an
    explicit yes should ever accept an ambiguous match — blank, 'n', or
    anything else must be treated as a decline."""
    assert intake._accepts_ambiguous_match("y") is True
    assert intake._accepts_ambiguous_match("Yes") is True
    assert intake._accepts_ambiguous_match("") is False
    assert intake._accepts_ambiguous_match("n") is False
    assert intake._accepts_ambiguous_match("sure") is False
