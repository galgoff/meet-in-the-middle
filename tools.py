"""
tools.py — Week 1: real, grounded tools for distance and timezone, plus
real error handling for geocoding.
"""

import json
import math
import os
import time

import requests
from timezonefinder import TimezoneFinder
from zoneinfo import ZoneInfo
from datetime import datetime

_CACHE_PATH = "geocode_cache.json"
_tf = TimezoneFinder()

NOMINATIM_RATE_LIMIT_SLEEP_SECONDS = 1.0  # required by Nominatim's usage policy, not tunable

# Lightweight call-level metrics — enough to answer "where did the time
# go" without guessing, not a full tracing system (that's Week 5's job:
# per-call input/output/latency logging for auditability). A cold cache
# means every candidate city pays NOMINATIM_RATE_LIMIT_SLEEP_SECONDS on
# top of the actual request — with ~30 candidate cities, that's 30+
# seconds of *mandatory* sleep alone before any real work happens. These
# counters make that visible instead of just feeling slow.
_stats = {
    "cache_hits": 0,
    "cache_misses": 0,
    "network_seconds": 0.0,
    "sleep_seconds": 0.0,
}


def reset_geocode_stats() -> None:
    """Zero the metrics. Call at the start of a run to scope the numbers
    to just that run instead of accumulating across calls."""
    _stats["cache_hits"] = 0
    _stats["cache_misses"] = 0
    _stats["network_seconds"] = 0.0
    _stats["sleep_seconds"] = 0.0


def get_geocode_stats() -> dict:
    """Snapshot of geocode_city's time spending this run: cache hits
    vs. misses, total time actually waiting on Nominatim's network
    response, and total time spent in its mandatory per-call rate-limit
    sleep (see NOMINATIM_RATE_LIMIT_SLEEP_SECONDS) — by policy, not a
    bug, but easy to mistake for one when a cold cache means dozens of
    calls back to back."""
    return dict(_stats)


def _load_cache() -> dict:
    if os.path.exists(_CACHE_PATH):
        with open(_CACHE_PATH) as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict) -> None:
    with open(_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def geocode_city(city: str) -> dict:
    """Look up a city's coordinates. Cached on disk. Flags ambiguous
    names (e.g. 'Cambridge' could mean UK or Massachusetts) instead of
    silently picking one, and returns a clear error instead of crashing
    on a network problem or an unknown city."""
    city = city.strip()
    if not city:
        return {"error": "Empty city name."}

    key = city.lower()
    cache = _load_cache()
    if key in cache:
        _stats["cache_hits"] += 1
        return cache[key]

    _stats["cache_misses"] += 1
    _request_start = time.perf_counter()
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": city, "format": "json", "limit": 5, "addressdetails": 1},
            headers={"User-Agent": "meet-in-the-middle-learning-project (galgof@gmail.com)"},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"Network error looking up '{city}': {e}"}
    finally:
        _stats["network_seconds"] += time.perf_counter() - _request_start
        time.sleep(NOMINATIM_RATE_LIMIT_SLEEP_SECONDS)  # respect Nominatim's usage policy
        _stats["sleep_seconds"] += NOMINATIM_RATE_LIMIT_SLEEP_SECONDS

    if not results:
        return {"error": f"No match found for '{city}'."}

    top = results[0]
    countries = {
        r.get("address", {}).get("country", r["display_name"].split(",")[-1].strip())
        for r in results[:3]
    }
    ambiguous = len(countries) > 1

    result = {
        "city": city,
        "lat": float(top["lat"]),
        "lon": float(top["lon"]),
        "display_name": top["display_name"],
        "ambiguous": ambiguous,
        # Country of the top match — used by ground_travel.py to check
        # whether ground travel is even on the table (island nations,
        # closed borders). Blank if Nominatim didn't return one; callers
        # treat that as "unknown, not ruled out" rather than an error.
        "country": top.get("address", {}).get("country", ""),
    }
    if ambiguous:
        result["alternatives"] = [
            {"display_name": r["display_name"], "lat": float(r["lat"]), "lon": float(r["lon"])}
            for r in results[1:3]
        ]

    cache[key] = result
    _save_cache(cache)
    return result


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometers. Real math, not a guess."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_utc_offset_hours(lat: float, lon: float) -> dict:
    """Current UTC offset for a coordinate, via an offline timezone
    lookup — no API, no rate limit, no hallucination possible."""
    tz_name = _tf.timezone_at(lat=lat, lng=lon)
    if tz_name is None:
        return {"error": f"No timezone found for ({lat}, {lon})"}
    now = datetime.now(ZoneInfo(tz_name))
    offset = now.utcoffset().total_seconds() / 3600
    return {"timezone": tz_name, "utc_offset_hours": offset}
