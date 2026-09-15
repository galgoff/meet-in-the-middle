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
        return cache[key]

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
        time.sleep(1)  # respect Nominatim's usage policy

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
