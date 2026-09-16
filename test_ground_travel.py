"""
test_ground_travel.py — mode-aware effort: ground vs. flight.

All pure math + lookups, no network — these should never be flaky,
same category as the fairness-score tests in test_tools.py.
"""

from ground_travel import ground_effort_hours, ground_travel_possible, normalize_travel_preference
from midpoint_agent import best_effort


def test_uk_france_allowed_via_channel_tunnel():
    """The case that started this: London-Paris has a real fixed link
    (Eurostar / Le Shuttle), so ground must NOT be ruled out here even
    though the UK has no natural land border to anywhere."""
    possible, reason = ground_travel_possible("United Kingdom", "France", 342)
    assert possible is True
    assert "fixed link" in reason


def test_uk_ireland_blocked_no_fixed_link():
    """Same island status as UK-France, but no tunnel/bridge exists —
    must be blocked."""
    possible, _ = ground_travel_possible("United Kingdom", "Ireland", 460)
    assert possible is False


def test_island_nation_blocked_even_at_short_distance():
    """Distance alone must not be the only signal — Cyprus to Turkey is
    short but there's open water and no fixed link."""
    possible, _ = ground_travel_possible("Cyprus", "Turkey", 80)
    assert possible is False


def test_closed_political_border_blocked_despite_short_distance():
    """The geopolitical case: land-adjacent but the border is closed to
    ordinary crossing regardless of how close the distance is."""
    possible, reason = ground_travel_possible("Israel", "Lebanon", 120)
    assert possible is False
    assert "closed" in reason or "impractical" in reason


def test_same_country_always_allowed():
    possible, reason = ground_travel_possible("Portugal", "Portugal", 274)
    assert possible is True
    assert reason == "same country"


def test_beyond_max_distance_blocked_regardless_of_countries():
    possible, _ = ground_travel_possible("France", "Germany", 5000)
    assert possible is False


def test_unknown_country_not_ruled_out():
    possible, reason = ground_travel_possible("", "", 300)
    assert possible is True
    assert "unknown" in reason


def test_ground_effort_increases_with_distance():
    assert ground_effort_hours(100) < ground_effort_hours(500)


def test_best_effort_picks_ground_when_faster_and_allowed():
    # short hop, same country -> ground should win over flight's fixed overhead
    result = best_effort(150, "Portugal", "Portugal")
    assert result["mode"] == "ground"


def test_best_effort_picks_flight_when_ground_is_blocked():
    # short distance, but Cyprus-Turkey has no fixed link -> must stay "flight"
    # even though a naive ground formula would look faster
    result = best_effort(80, "Cyprus", "Turkey")
    assert result["mode"] == "flight"
    assert "ruled out" in result["note"]


def test_best_effort_picks_flight_for_long_haul():
    result = best_effort(9000, "Portugal", "Japan")
    assert result["mode"] == "flight"


def test_normalize_travel_preference_maps_free_text_to_canonical_values():
    assert normalize_travel_preference("ground") == "prefer_ground"
    assert normalize_travel_preference("Train") == "prefer_ground"
    assert normalize_travel_preference("speed") == "prefer_speed"
    assert normalize_travel_preference("Fastest") == "prefer_speed"
    assert normalize_travel_preference("") == "no_preference"
    assert normalize_travel_preference("something unrecognized") == "no_preference"


def test_prefer_ground_flips_london_paris_to_ground():
    """The exact case that started this: London-Paris stays "flight"
    under a neutral comparison, but someone who's told us they'd rather
    take the train should see it flip."""
    neutral = best_effort(342, "United Kingdom", "France", "no_preference")
    assert neutral["mode"] == "flight"

    preferred = best_effort(342, "United Kingdom", "France", "prefer_ground")
    assert preferred["mode"] == "ground"
    # the reported hours must be the REAL ground time, never an inflated
    # or fabricated number — the preference only changes which mode wins
    assert preferred["hours"] == round(1.0 + 342 / 90.0, 10)


def test_prefer_speed_behaves_like_no_preference():
    a = best_effort(342, "United Kingdom", "France", "no_preference")
    b = best_effort(342, "United Kingdom", "France", "prefer_speed")
    assert a["mode"] == b["mode"] == "flight"
    assert a["hours"] == b["hours"]


def test_preference_cannot_override_a_hard_block():
    result = best_effort(80, "Cyprus", "Turkey", "prefer_ground")
    assert result["mode"] == "flight"
    assert "ruled out" in result["note"]
