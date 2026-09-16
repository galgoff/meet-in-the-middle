"""
test_metrics.py — geocode call metrics (cache hits/misses, network and
rate-limit-sleep time). Network and sleep are both mocked here so these
tests run instantly and don't depend on Nominatim being reachable —
test_tools.py already covers the real network path.
"""

import json
from unittest.mock import MagicMock, patch

import tools


def _fake_response(payload):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


def test_cache_hit_does_not_touch_network_or_sleep(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "_CACHE_PATH", str(tmp_path / "cache.json"))
    tools.reset_geocode_stats()

    cache = {
        "testville": {
            "city": "Testville", "lat": 1.0, "lon": 2.0,
            "display_name": "Testville", "ambiguous": False, "country": "Testland",
        }
    }
    with open(tools._CACHE_PATH, "w") as f:
        json.dump(cache, f)

    with patch("tools.requests.get") as mock_get, patch("tools.time.sleep") as mock_sleep:
        result = tools.geocode_city("Testville")

    assert result["city"] == "Testville"
    mock_get.assert_not_called()
    mock_sleep.assert_not_called()

    stats = tools.get_geocode_stats()
    assert stats["cache_hits"] == 1
    assert stats["cache_misses"] == 0
    assert stats["sleep_seconds"] == 0


def test_cache_miss_records_one_sleep_and_network_call(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "_CACHE_PATH", str(tmp_path / "cache.json"))
    tools.reset_geocode_stats()

    payload = [{
        "lat": "10.0", "lon": "20.0", "display_name": "Freshville, Testland",
        "address": {"country": "Testland"},
    }]

    with patch("tools.requests.get", return_value=_fake_response(payload)) as mock_get, \
         patch("tools.time.sleep") as mock_sleep:
        result = tools.geocode_city("Freshville")

    assert result["city"] == "Freshville"
    assert result["country"] == "Testland"
    mock_get.assert_called_once()
    mock_sleep.assert_called_once_with(tools.NOMINATIM_RATE_LIMIT_SLEEP_SECONDS)

    stats = tools.get_geocode_stats()
    assert stats["cache_misses"] == 1
    assert stats["cache_hits"] == 0
    assert stats["sleep_seconds"] == tools.NOMINATIM_RATE_LIMIT_SLEEP_SECONDS


def test_reset_geocode_stats_zeroes_everything():
    tools._stats["cache_hits"] = 5
    tools._stats["network_seconds"] = 12.3
    tools.reset_geocode_stats()
    stats = tools.get_geocode_stats()
    assert all(v == 0 for v in stats.values())
