"""
test_tools.py — Week 1 edge cases.

Four of these hit the live Nominatim geocoder (an external dependency,
so bounds are deliberately a bit loose to tolerate small real-world
variation). The fairness test is pure math and needs no network at
all — worth noticing the difference: it's the one test here that can
never be flaky.
"""

from tools import geocode_city, haversine_km
from midpoint_agent import fairness_score


def test_same_country_distance_is_small():
    lisbon = geocode_city("Lisbon")
    porto = geocode_city("Porto")
    dist = haversine_km(lisbon["lat"], lisbon["lon"], porto["lat"], porto["lon"])
    assert 200 < dist < 350  # real-world distance is ~274 km


def test_opposite_hemispheres_distance_is_large_and_sane():
    wellington = geocode_city("Wellington, New Zealand")
    madrid = geocode_city("Madrid")
    dist = haversine_km(wellington["lat"], wellington["lon"], madrid["lat"], madrid["lon"])
    assert 19000 < dist < 20200  # real-world distance is ~19,855 km


def test_ambiguous_city_name_does_not_crash():
    result = geocode_city("Cambridge")
    assert "error" not in result
    assert isinstance(result["lat"], float)
    assert isinstance(result["ambiguous"], bool)


def test_unknown_city_returns_error_not_crash():
    result = geocode_city("Xyzzyqqqnotarealcity123")
    assert "error" in result


def test_fairness_score_rewards_equal_effort_over_lower_average():
    fair = fairness_score([5.9, 6.0])                 # tiny gap
    unfair_but_similar_average = fairness_score([2.0, 9.0])  # big gap
    assert fair < unfair_but_similar_average
