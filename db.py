"""
db.py — Week 2: SQLite persistence for multi-party trip intake.

A trip starts `open` and collects one submission per person. It becomes
`complete` the instant either (a) submissions reach `expected_parties`,
or (b) the organizer manually locks it early with `lock_trip()`. Once
`complete`, no further submissions are accepted — on purpose. Letting a
late arrival reopen a trip after the group has already been scored would
mean silently reshuffling results out from under everyone who already
looked at them. The fix for "one more person wants in" is a new trip,
not reopening this one.

PII minimization (Week 2 guardrail): the schema has no passport_number
column, full stop — we only ever ask for and store `nationality`
(the visa-relevant fact), never a passport number. See guardrails.py for
the defense-in-depth scrub applied to free-text fields too.
"""

import sqlite3
import time
import uuid
from contextlib import contextmanager

from ground_travel import normalize_travel_preference
from guardrails import scrub_passport_like

DEFAULT_DB_PATH = "trip.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
    id              TEXT PRIMARY KEY,
    expected_parties INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open',   -- 'open' | 'complete'
    locked_early    INTEGER NOT NULL DEFAULT 0,      -- 1 if completed via manual override
    created_at      REAL NOT NULL,
    completed_at    REAL
);

CREATE TABLE IF NOT EXISTS submissions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id             TEXT NOT NULL REFERENCES trips(id),
    person_name         TEXT NOT NULL,
    origin_city         TEXT NOT NULL,
    date_flexibility    TEXT,
    budget_ceiling_usd  REAL,
    nationality         TEXT,
    hard_constraints    TEXT,
    travel_preference   TEXT DEFAULT 'no_preference',
    submitted_at        REAL NOT NULL,
    UNIQUE(trip_id, person_name)
);
"""


class TripError(Exception):
    """Raised for expected, user-facing problems (trip full, not found, etc.)."""


@contextmanager
def _connect(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA)
        # Lightweight migration for a trip.db created before
        # travel_preference existed. SQLite has no "ADD COLUMN IF NOT
        # EXISTS", so check first rather than relying on catching an
        # OperationalError. Existing rows get the same default as new
        # ones ('no_preference') — old submissions never silently gain
        # a preference nobody stated.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(submissions)")}
        if "travel_preference" not in columns:
            conn.execute(
                "ALTER TABLE submissions ADD COLUMN travel_preference TEXT DEFAULT 'no_preference'"
            )


def create_trip(expected_parties: int, db_path: str = DEFAULT_DB_PATH) -> str:
    if expected_parties < 2:
        raise TripError("A trip needs at least 2 expected parties.")
    init_db(db_path)
    trip_id = uuid.uuid4().hex[:8]
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO trips (id, expected_parties, status, created_at) VALUES (?, ?, 'open', ?)",
            (trip_id, expected_parties, time.time()),
        )
    return trip_id


def get_trip(trip_id: str, db_path: str = DEFAULT_DB_PATH) -> dict:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    if row is None:
        raise TripError(f"No trip found with id '{trip_id}'.")
    return dict(row)


def get_submissions(trip_id: str, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM submissions WHERE trip_id = ? ORDER BY submitted_at", (trip_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def add_submission(
    trip_id: str,
    person_name: str,
    origin_city: str,
    date_flexibility: str = "",
    budget_ceiling_usd: float | None = None,
    nationality: str = "",
    hard_constraints: str = "",
    travel_preference: str = "",
    db_path: str = DEFAULT_DB_PATH,
) -> dict:
    """Upsert one person's submission. Raises TripError if the trip is
    already complete (locked or full) — that's the guardrail against a
    late submission silently reshuffling results everyone already saw.

    PII guardrail: free-text fields — including nationality, which is
    exactly the field someone half-asleep might paste a passport number
    into instead of a country name — are scrubbed for passport/ID-like
    substrings before they ever touch disk. The returned dict's
    "redacted" key is True if anything was caught, so callers
    (intake.py) can tell the person what happened.

    travel_preference is free-typed and normalized to one of
    ground_travel.VALID_TRAVEL_PREFERENCES (see normalize_travel_preference)
    before storage — blank or unrecognized input becomes "no_preference",
    never a guessed stronger preference."""
    trip = get_trip(trip_id, db_path)
    if trip["status"] == "complete":
        raise TripError(
            f"Trip '{trip_id}' is already complete and no longer accepting submissions. "
            "If someone new wants in, start a new trip instead — this one is locked so "
            "results don't shift under people who already responded."
        )
    if not person_name.strip():
        raise TripError("Person name is required.")
    if not origin_city.strip():
        raise TripError("Origin city is required.")

    hard_constraints, redacted_1 = scrub_passport_like(hard_constraints.strip())
    date_flexibility, redacted_2 = scrub_passport_like(date_flexibility.strip())
    nationality, redacted_3 = scrub_passport_like(nationality.strip())
    redacted = redacted_1 or redacted_2 or redacted_3
    travel_preference = normalize_travel_preference(travel_preference)

    with _connect(db_path) as conn:
        conn.execute(
            """INSERT INTO submissions
                 (trip_id, person_name, origin_city, date_flexibility,
                  budget_ceiling_usd, nationality, hard_constraints, travel_preference, submitted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(trip_id, person_name) DO UPDATE SET
                 origin_city=excluded.origin_city,
                 date_flexibility=excluded.date_flexibility,
                 budget_ceiling_usd=excluded.budget_ceiling_usd,
                 nationality=excluded.nationality,
                 hard_constraints=excluded.hard_constraints,
                 travel_preference=excluded.travel_preference,
                 submitted_at=excluded.submitted_at
            """,
            (
                trip_id, person_name.strip(), origin_city.strip(), date_flexibility,
                budget_ceiling_usd, nationality, hard_constraints, travel_preference, time.time(),
            ),
        )
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM submissions WHERE trip_id = ?", (trip_id,)
        ).fetchone()["n"]

        if count >= trip["expected_parties"]:
            conn.execute(
                "UPDATE trips SET status = 'complete', completed_at = ? WHERE id = ? AND status = 'open'",
                (time.time(), trip_id),
            )

    result = get_trip(trip_id, db_path)
    result["redacted"] = redacted
    return result


def lock_trip(trip_id: str, db_path: str = DEFAULT_DB_PATH) -> dict:
    """Manually finalize a trip before it reaches expected_parties — for
    the 'someone's gone quiet and isn't responding' case. Irreversible by
    design: once locked, whoever has submitted is the group, permanently."""
    trip = get_trip(trip_id, db_path)
    if trip["status"] == "complete":
        raise TripError(f"Trip '{trip_id}' is already complete.")

    submissions = get_submissions(trip_id, db_path)
    if len(submissions) < 2:
        raise TripError("Need at least 2 submissions before a trip can be locked.")

    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE trips SET status = 'complete', locked_early = 1, completed_at = ? WHERE id = ?",
            (time.time(), trip_id),
        )
    return get_trip(trip_id, db_path)


def trip_status_summary(trip_id: str, db_path: str = DEFAULT_DB_PATH) -> str:
    trip = get_trip(trip_id, db_path)
    submissions = get_submissions(trip_id, db_path)
    names = ", ".join(s["person_name"] for s in submissions) or "(none yet)"
    lines = [
        f"Trip {trip_id}: {len(submissions)}/{trip['expected_parties']} submitted — status: {trip['status']}"
        + (" (locked early)" if trip["locked_early"] else ""),
        f"  Submitted so far: {names}",
    ]
    return "\n".join(lines)
