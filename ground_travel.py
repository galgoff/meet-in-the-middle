"""
ground_travel.py — mode-aware effort: is train/driving on the table at
all, and if so, how does it compare to flying?

Prompted by a real gap: pure distance-based flight math gets London-Paris
wrong (Eurostar beats flying, city-center to city-center) and can't tell
"500 km on open road" from "500 km across a closed border or open water."

This is a coarse heuristic, not routing data, and says so everywhere:
  - ground_effort_hours() uses one blended avg speed for all of road/rail
    worldwide — not a real timetable or route. A high-speed-rail corridor
    (Eurostar) and a two-lane mountain road get the same number. That's
    a real limitation, not an oversight — see PRODUCT_BRIEF for how this
    should evolve if it ever needs to be precise (real routing/rail APIs).
  - ground_travel_possible() encodes a SMALL, ILLUSTRATIVE, NOT EXHAUSTIVE
    set of real blockers: island nations with no land border to anywhere
    (allowing named fixed links like the Channel Tunnel as exceptions),
    and a handful of closed/impractical political borders. Silence on a
    pair doesn't mean "verified drivable" — it means "no known blocker
    in this list." Same disclosed-gap pattern as the Week 4 visa/border
    spike: ship an honest, curated ruleset instead of pretending there's
    a real data source, and say so instead of hiding it.
"""

GROUND_SPEED_KMH = 90.0      # blended road/rail average — coarse, see module docstring
GROUND_OVERHEAD_HOURS = 1.0  # station/parking overhead — well below flight's airport overhead
GROUND_MAX_KM = 800.0        # beyond this, ground isn't even considered

# Per-person travel-mode preference. Deliberately NOT a global "flying is
# X% more annoying" constant — that would just be a smaller-scope version
# of the same one-size-fits-all assumption problem this module already
# works to avoid for geography. Whether the extra hassle of flying (security,
# check-in, uncertainty) outweighs a time difference is personal, not
# universal, so it's collected per person at intake instead of assumed.
VALID_TRAVEL_PREFERENCES = {"no_preference", "prefer_ground", "prefer_speed"}
DEFAULT_TRAVEL_PREFERENCE = "no_preference"

# A stand-in for the planning/security/uncertainty burden of flying that
# raw clock time doesn't capture, applied ONLY when comparing modes for
# someone who has stated they prefer ground. Not measured, not universal —
# same "coarse and disclosed, not hidden" pattern as GROUND_SPEED_KMH.
# It shifts which mode WINS the comparison; it never inflates the hours
# actually reported for a trip (see best_effort() in midpoint_agent.py).
FLIGHT_HASSLE_PENALTY_HOURS = 2.0


def normalize_travel_preference(raw: str) -> str:
    """Map free-typed intake text to one of VALID_TRAVEL_PREFERENCES.
    Unrecognized or blank input defaults to DEFAULT_TRAVEL_PREFERENCE —
    we never guess a stronger preference than someone actually stated."""
    key = (raw or "").strip().lower()
    if key in ("ground", "prefer_ground", "prefer ground", "train", "train/driving", "avoid flying"):
        return "prefer_ground"
    if key in ("speed", "prefer_speed", "prefer speed", "fast", "fastest", "whatever's fastest"):
        return "prefer_speed"
    return DEFAULT_TRAVEL_PREFERENCE

# Countries with no land border to any other country. Blocked from ground
# travel to/from anywhere UNLESS the pair is in FIXED_LINKS below.
NO_LAND_BORDER_COUNTRIES = {
    "United Kingdom", "Ireland", "Iceland", "Japan", "Australia",
    "New Zealand", "Sri Lanka", "Cyprus", "Malta", "Philippines",
    "Indonesia", "Madagascar", "Cuba", "Taiwan",
}

# Named exceptions: a real fixed transport link (tunnel/bridge/car-train)
# makes ground travel genuinely possible despite no natural land border.
# This is the London-Paris case that prompted this module: the Channel
# Tunnel carries both Eurostar (passenger rail) and Le Shuttle (cars).
FIXED_LINKS = {
    frozenset({"United Kingdom", "France"}),  # Channel Tunnel
}

# Land-adjacent or land-reachable country pairs whose shared border is
# closed or impractical for ordinary civilian crossing. Short and
# illustrative on purpose — real coverage is Week 4 territory.
CLOSED_OR_IMPRACTICAL_BORDERS = {
    frozenset({"Israel", "Lebanon"}),
    frozenset({"Israel", "Syria"}),
    frozenset({"Armenia", "Azerbaijan"}),
    frozenset({"Armenia", "Turkey"}),
    frozenset({"India", "Pakistan"}),
    frozenset({"North Korea", "South Korea"}),
    frozenset({"Morocco", "Algeria"}),
}


def ground_effort_hours(distance_km: float) -> float:
    """Coarse door-to-door estimate for train/driving. See module
    docstring — one blended speed for all ground modes worldwide."""
    return GROUND_OVERHEAD_HOURS + (distance_km / GROUND_SPEED_KMH)


def ground_travel_possible(country_a: str, country_b: str, distance_km: float) -> tuple[bool, str]:
    """Whether ground travel between two countries is even worth
    comparing to flying. Returns (possible, reason) — the reason is
    always populated so callers can show their work instead of a bare
    yes/no. See module docstring for what this heuristic does and
    doesn't cover."""
    if distance_km > GROUND_MAX_KM:
        return False, f"beyond the {GROUND_MAX_KM:.0f} km ground-travel cutoff"

    if not country_a or not country_b:
        return True, "country unknown — not ruled out (see ground_travel.py limitations)"

    if country_a == country_b:
        return True, "same country"

    pair = frozenset({country_a, country_b})

    if pair in FIXED_LINKS:
        return True, "connected by a known fixed link (tunnel/bridge/car-train)"

    if country_a in NO_LAND_BORDER_COUNTRIES or country_b in NO_LAND_BORDER_COUNTRIES:
        island = country_a if country_a in NO_LAND_BORDER_COUNTRIES else country_b
        return False, f"{island} has no land border to any other country and no known fixed link here"

    if pair in CLOSED_OR_IMPRACTICAL_BORDERS:
        return False, f"{country_a}\u2013{country_b} border is closed or impractical for civilian crossing"

    return True, "no known blocker (not the same as verified drivable — see limitations)"
