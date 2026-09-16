"""
midpoint_agent.py — Week 1: rank candidate cities by fairness of effort,
not raw distance. Week 2 adds group scoring straight from a completed
trip's stored submissions. See module history / product brief for the
fairness philosophy and disclosed assumptions.
"""

import sys
import time

from db import TripError, get_submissions, get_trip
from ground_travel import (
    DEFAULT_TRAVEL_PREFERENCE,
    FLIGHT_HASSLE_PENALTY_HOURS,
    ground_effort_hours,
    ground_travel_possible,
)
from tools import geocode_city, get_geocode_stats, haversine_km, reset_geocode_stats

AIRPORT_OVERHEAD_HOURS = 3.0
CRUISE_SPEED_KMH = 800.0

CANDIDATE_CITIES = [
    "London", "Paris", "Amsterdam", "Frankfurt", "Istanbul", "Dubai",
    "Doha", "Athens", "Rome", "Madrid", "Vienna", "Zurich", "Reykjavik",
    "New York", "Miami", "Los Angeles", "Toronto", "Mexico City",
    "Sao Paulo", "Cairo", "Nairobi", "Johannesburg", "Mumbai", "Delhi",
    "Bangkok", "Singapore", "Tokyo", "Seoul", "Hong Kong", "Sydney",
]


def effort_hours(distance_km: float) -> float:
    """Rough door-to-door estimate for FLYING. See module docstring for
    assumptions. (Renamed in spirit but not in name — kept as
    `effort_hours` for backward compatibility; `best_effort` below is
    what actually picks a mode.)"""
    return AIRPORT_OVERHEAD_HOURS + (distance_km / CRUISE_SPEED_KMH)


def best_effort(
    distance_km: float,
    country_a: str = "",
    country_b: str = "",
    travel_preference: str = DEFAULT_TRAVEL_PREFERENCE,
) -> dict:
    """Pick whichever of flying or ground travel is faster — but only
    consider ground at all if ground_travel_possible() clears it first.
    Always returns which mode won and why, so the caller can show its
    work instead of a bare number. Pure math + one lookup, no I/O.

    travel_preference only shifts which mode WINS the comparison for a
    "prefer_ground" person (via FLIGHT_HASSLE_PENALTY_HOURS — see
    ground_travel.py for why that's a per-person input, not a global
    assumption). The "hours" this returns are always the real,
    unpenalized time for whichever mode is actually selected — the
    preference never inflates a number into something that didn't
    happen; it only changes which real number gets shown."""
    flight_hours = effort_hours(distance_km)
    possible, reason = ground_travel_possible(country_a, country_b, distance_km)

    if not possible:
        return {"hours": flight_hours, "mode": "flight", "note": f"ground ruled out: {reason}"}

    ground_hours = ground_effort_hours(distance_km)

    compare_flight_hours = flight_hours
    pref_note = ""
    if travel_preference == "prefer_ground":
        compare_flight_hours = flight_hours + FLIGHT_HASSLE_PENALTY_HOURS
        pref_note = f", weighted for stated ground preference (+{FLIGHT_HASSLE_PENALTY_HOURS:.0f}h flight-hassle penalty in this comparison only)"

    if ground_hours < compare_flight_hours:
        return {"hours": ground_hours, "mode": "ground", "note": f"ground allowed ({reason}) and faster{pref_note}"}
    return {"hours": flight_hours, "mode": "flight", "note": f"ground allowed ({reason}) but slower{pref_note}"}


def fairness_score(efforts, spread_weight=1.0, total_weight=0.5) -> float:
    """Pure math, no I/O — deliberately, so it's testable without a
    network call. Lower is fairer. Rewards a small gap between people's
    effort over a lower average with a big gap."""
    spread = max(efforts) - min(efforts)
    mean_effort = sum(efforts) / len(efforts)
    return spread_weight * spread + total_weight * mean_effort


def score_candidates(party_cities, travel_preferences=None, spread_weight=1.0, total_weight=0.5):
    """travel_preferences, if given, must align 1:1 with party_cities —
    each person's stated flight-vs-ground preference (see
    ground_travel.VALID_TRAVEL_PREFERENCES). Defaults to
    DEFAULT_TRAVEL_PREFERENCE for everyone when omitted, which is the
    raw-city-args CLI path where no per-person data exists to draw on."""
    if travel_preferences is None:
        travel_preferences = [DEFAULT_TRAVEL_PREFERENCE] * len(party_cities)
    if len(travel_preferences) != len(party_cities):
        raise ValueError("travel_preferences must have exactly one entry per party_cities")

    parties = []
    for city, preference in zip(party_cities, travel_preferences):
        geo = geocode_city(city)
        if "error" in geo:
            print(f"[warning] could not geocode '{city}': {geo['error']}")
            continue
        if geo.get("ambiguous"):
            print(f"[warning] '{city}' is ambiguous — using {geo['display_name']}. "
                  f"Alternatives: {[a['display_name'] for a in geo['alternatives']]}")
        geo["travel_preference"] = preference or DEFAULT_TRAVEL_PREFERENCE
        parties.append(geo)

    if len(parties) < 2:
        raise ValueError("Need at least 2 successfully-geocoded party cities.")

    results = []
    for candidate_name in CANDIDATE_CITIES:
        candidate = geocode_city(candidate_name)
        if "error" in candidate:
            continue

        per_party = []
        for p in parties:
            dist = haversine_km(p["lat"], p["lon"], candidate["lat"], candidate["lon"])
            best = best_effort(
                dist, p.get("country", ""), candidate.get("country", ""),
                p.get("travel_preference", DEFAULT_TRAVEL_PREFERENCE),
            )
            per_party.append({
                "party_city": p["city"],
                "distance_km": round(dist),
                "effort_hours": round(best["hours"], 1),
                "mode": best["mode"],
                "mode_note": best["note"],
            })

        efforts = [pp["effort_hours"] for pp in per_party]
        score = fairness_score(efforts, spread_weight, total_weight)

        results.append({
            "candidate": candidate["city"],
            "score": round(score, 2),
            "per_party": per_party,
            "price_usd": "pending — Week 3 (Duffel integration)",
        })

    results.sort(key=lambda r: r["score"])
    return results


def score_group(trip_id: str, db_path: str = "trip.db"):
    """Week 2: pull a completed trip's submissions from SQLite and run
    the same fairness scoring used for raw city args. Refuses to run on
    a trip that isn't complete yet — no partial-group ranking, since
    that's exactly the "shuffles under people" problem the lock/complete
    guardrail in db.py exists to prevent."""
    trip = get_trip(trip_id, db_path)
    if trip["status"] != "complete":
        submissions = get_submissions(trip_id, db_path)
        raise ValueError(
            f"Trip '{trip_id}' isn't complete yet ({len(submissions)}/{trip['expected_parties']} "
            "submitted). Either wait for everyone, or run "
            f"`python3 intake.py lock {trip_id}` to finalize early."
        )

    submissions = get_submissions(trip_id, db_path)
    cities = [s["origin_city"] for s in submissions]
    preferences = [s.get("travel_preference") or DEFAULT_TRAVEL_PREFERENCE for s in submissions]
    ranked = score_candidates(cities, preferences)
    return trip, submissions, ranked


def _print_group_context(submissions) -> None:
    print("Party (from stored submissions):")
    for s in submissions:
        budget = f"${s['budget_ceiling_usd']:.0f}" if s["budget_ceiling_usd"] else "not set"
        nationality = s["nationality"] or "not set"
        dates = s["date_flexibility"] or "not set"
        travel_pref = s.get("travel_preference") or DEFAULT_TRAVEL_PREFERENCE
        print(f"  {s['person_name']:12s} from {s['origin_city']}")
        print(f"       budget ceiling: {budget}  |  nationality: {nationality}  |  dates: {dates}")
        print(f"       travel preference: {travel_pref}")
        if s["hard_constraints"]:
            print(f"       hard constraints: {s['hard_constraints']}")
    print(
        "\n  (Budget and nationality are stored but not yet enforced — Duffel pricing lands "
        "in Week 3, visa flags in Week 4. Not silently ignoring them, just not built yet.)\n"
    )


GROUND_TRAVEL_CAVEAT = (
    "Note: door-to-door hours consider both flying and ground travel (train/driving) "
    "where a coarse heuristic allows it — see ground_travel.py. This is a blended "
    "average speed, not a real timetable, and the list of blocked routes (islands, "
    "closed borders) is illustrative, not exhaustive. 'flight' shown for a route "
    "doesn't mean ground was verified impossible, just not cleared by this heuristic.\n"
)


def _print_timing_summary(elapsed_seconds: float) -> None:
    """Answers 'why did that take so long' with numbers instead of a
    shrug. On a cold cache, sleep_seconds will dominate — that's
    Nominatim's mandatory 1s-per-call rate limit times however many
    cities weren't cached, not wasted work. A warm cache (repeat runs,
    or candidates you've already looked up) should show ~0 misses and
    finish in well under a second of actual geocoding time."""
    stats = get_geocode_stats()
    total_calls = stats["cache_hits"] + stats["cache_misses"]
    print(
        f"[timing] total run: {elapsed_seconds:.1f}s  |  "
        f"geocode calls: {total_calls} ({stats['cache_hits']} cache hit, {stats['cache_misses']} cache miss)  |  "
        f"network: {stats['network_seconds']:.1f}s  |  "
        f"rate-limit sleep: {stats['sleep_seconds']:.1f}s "
        f"({stats['cache_misses']} uncached call(s) \u00d7 {1.0:.0f}s, required by Nominatim's usage policy)"
    )


def _print_ranked(ranked) -> None:
    print(GROUND_TRAVEL_CAVEAT)
    for i, r in enumerate(ranked[:5], start=1):
        print(f"{i}. {r['candidate']}  (fairness score: {r['score']}, lower = fairer)")
        for pp in r["per_party"]:
            print(f"     {pp['party_city']:12s} -> {pp['distance_km']:>5} km, ~{pp['effort_hours']} hrs door-to-door ({pp['mode']})")
        print(f"     price: {r['price_usd']}")
        print()


if __name__ == "__main__":
    reset_geocode_stats()
    _run_start = time.perf_counter()

    args = sys.argv[1:]

    if args and args[0] == "--trip":
        if len(args) < 2:
            print("Usage: python3 midpoint_agent.py --trip <trip_id>")
            sys.exit(1)
        try:
            trip, submissions, ranked = score_group(args[1])
        except (ValueError, TripError) as e:
            print(f"Error: {e}")
            sys.exit(1)

        print(f"Trip {args[1]} — {len(submissions)} parties\n")
        _print_group_context(submissions)
        _print_ranked(ranked)
    else:
        cities = args
        if len(cities) < 2:
            print("Usage: python3 midpoint_agent.py \"City One\" \"City Two\" [\"City Three\" ...]")
            print("   or: python3 midpoint_agent.py --trip <trip_id>")
            sys.exit(1)

        print(f"Finding fair meeting points for: {', '.join(cities)}")
        print("(first run will be slow while candidate cities get geocoded and cached)\n")

        ranked = score_candidates(cities)
        _print_ranked(ranked)

    _print_timing_summary(time.perf_counter() - _run_start)
