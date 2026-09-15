"""
midpoint_agent.py — Week 1: rank candidate cities by fairness of effort,
not raw distance. See module history / product brief for the fairness
philosophy and disclosed assumptions.
"""

import sys

from tools import geocode_city, haversine_km

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
    """Rough door-to-door estimate. See module docstring for assumptions."""
    return AIRPORT_OVERHEAD_HOURS + (distance_km / CRUISE_SPEED_KMH)


def fairness_score(efforts, spread_weight=1.0, total_weight=0.5) -> float:
    """Pure math, no I/O — deliberately, so it's testable without a
    network call. Lower is fairer. Rewards a small gap between people's
    effort over a lower average with a big gap."""
    spread = max(efforts) - min(efforts)
    mean_effort = sum(efforts) / len(efforts)
    return spread_weight * spread + total_weight * mean_effort


def score_candidates(party_cities, spread_weight=1.0, total_weight=0.5):
    parties = []
    for city in party_cities:
        geo = geocode_city(city)
        if "error" in geo:
            print(f"[warning] could not geocode '{city}': {geo['error']}")
            continue
        if geo.get("ambiguous"):
            print(f"[warning] '{city}' is ambiguous — using {geo['display_name']}. "
                  f"Alternatives: {[a['display_name'] for a in geo['alternatives']]}")
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
            per_party.append({
                "party_city": p["city"],
                "distance_km": round(dist),
                "effort_hours": round(effort_hours(dist), 1),
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


if __name__ == "__main__":
    cities = sys.argv[1:]
    if len(cities) < 2:
        print("Usage: python3 midpoint_agent.py \"City One\" \"City Two\" [\"City Three\" ...]")
        sys.exit(1)

    print(f"Finding fair meeting points for: {', '.join(cities)}")
    print("(first run will be slow while candidate cities get geocoded and cached)\n")

    ranked = score_candidates(cities)
    for i, r in enumerate(ranked[:5], start=1):
        print(f"{i}. {r['candidate']}  (fairness score: {r['score']}, lower = fairer)")
        for pp in r["per_party"]:
            print(f"     {pp['party_city']:12s} -> {pp['distance_km']:>5} km, ~{pp['effort_hours']} hrs door-to-door")
        print(f"     price: {r['price_usd']}")
        print()
