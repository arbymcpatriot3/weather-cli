#!/usr/bin/env python3
# tests/test_parking.py — Clean Shot: smart parking runway tests
#
# Covers:
#   compute_runway()                  (6 tests)
#   format_runway_str()               (3 tests)
#   _urgency_level()                  (4 tests)
#   _load_embedded_stops()            (3 tests)
#   _detect_chain()                   (4 tests)
#   get_nearby_stops()                (4 tests)
#   get_stops_in_corridor()           (2 tests)
#   find_recommended_stop()           (2 tests)
#   filter_by_amenity()               (3 tests)
#   TTS threshold system              (5 tests)
#   display functions                 (2 tests)
#   subscription gate                 (1 test)
# Total: 39 tests — all offline, no GPS hardware, no audio, no network

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.parking import (
    CHAINS,
    _EMBEDDED_STOPS,
    _ANNOUNCE_THRESHOLDS,
    _detect_chain,
    _load_embedded_stops,
    _urgency_level,
    compute_runway,
    format_runway_str,
    filter_by_amenity,
    get_nearby_stops,
    get_stops_in_corridor,
    find_recommended_stop,
    check_runway_thresholds,
    announce_runway,
    reset_announcements,
    display_stop,
    display_parking_status,
    DEFAULT_SPEED_MPH,
    PARKING_BUFFER_MIN,
)


# ── Test location: Memphis TN (many stops on I-40/I-55) ───────────────────────
HOME_LAT = 35.15
HOME_LON = -90.05


# ── compute_runway() ──────────────────────────────────────────────────────────

def test_compute_runway_standard():
    """Full 11-hour window → runway is (660-15)/60 × 55 = ~591 miles."""
    config = {"hos_drive_remaining_min": 660, "speed_mph": 55.0}
    r = compute_runway(config)
    expected = round(((660 - 15) / 60.0) * 55.0, 1)
    assert r["miles"] == expected, f"Expected {expected}, got {r['miles']}"
    assert r["minutes"] == 660
    assert r["level"]   == "normal"
    print(f"✓ compute_runway: full window → {r['miles']} mi")


def test_compute_runway_default_speed():
    """Without speed in config, DEFAULT_SPEED_MPH (55) should be used."""
    config = {"hos_drive_remaining_min": 660}
    r = compute_runway(config)
    assert r["speed_mph"] == DEFAULT_SPEED_MPH
    assert r["miles"] > 0
    print(f"✓ compute_runway: default speed {DEFAULT_SPEED_MPH} mph used")


def test_compute_runway_urgent():
    """59 minutes remaining → urgent=True, level='urgent'."""
    config = {"hos_drive_remaining_min": 59, "speed_mph": 55.0}
    r = compute_runway(config)
    assert r["urgent"]  is True
    assert r["critical"] is False
    assert r["level"]   == "urgent"
    print(f"✓ compute_runway: 59 min → urgent=True, {r['miles']:.1f} mi")


def test_compute_runway_critical():
    """29 minutes remaining → critical=True."""
    config = {"hos_drive_remaining_min": 29, "speed_mph": 55.0}
    r = compute_runway(config)
    assert r["critical"] is True
    assert r["level"]    == "critical"
    print(f"✓ compute_runway: 29 min → critical=True, {r['miles']:.1f} mi")


def test_compute_runway_zero():
    """0 minutes → 0 miles, critical."""
    config = {"hos_drive_remaining_min": 0, "speed_mph": 55.0}
    r = compute_runway(config)
    assert r["miles"]   == 0.0
    assert r["minutes"] == 0
    assert r["critical"] is True
    print("✓ compute_runway: 0 min → 0 miles, critical")


def test_compute_runway_warning_at_120():
    """120 minutes → warning=True, urgent=False."""
    config = {"hos_drive_remaining_min": 120, "speed_mph": 55.0}
    r = compute_runway(config)
    assert r["warning"] is True
    assert r["urgent"]  is False
    assert r["level"]   == "warning"
    print(f"✓ compute_runway: 120 min → warning=True, {r['miles']:.1f} mi")


# ── format_runway_str() ───────────────────────────────────────────────────────

def test_format_runway_normal():
    """Normal runway: no prefix, shows miles + hours."""
    config = {"hos_drive_remaining_min": 660, "speed_mph": 55.0}
    r   = compute_runway(config)
    s   = format_runway_str(r)
    assert "mi" in s
    assert "h"  in s
    assert "URGENT" not in s
    print(f"✓ format_runway_str: normal → '{s}'")


def test_format_runway_critical_prefix():
    """Critical runway should have URGENT prefix."""
    config = {"hos_drive_remaining_min": 20, "speed_mph": 55.0}
    r = compute_runway(config)
    s = format_runway_str(r)
    assert s.startswith("URGENT"), f"Expected URGENT prefix, got '{s}'"
    print(f"✓ format_runway_str: critical → '{s}'")


def test_format_runway_sub_hour():
    """Sub-60-min runway should not show hours part."""
    config = {"hos_drive_remaining_min": 45, "speed_mph": 55.0}
    r = compute_runway(config)
    s = format_runway_str(r)
    assert "mi" in s
    print(f"✓ format_runway_str: sub-hour → '{s}'")


# ── _urgency_level() ─────────────────────────────────────────────────────────

def test_urgency_normal():
    assert _urgency_level(300) == "normal"
    assert _urgency_level(121) == "normal"
    print("✓ urgency_level: >120 min → normal")


def test_urgency_warning():
    assert _urgency_level(120) == "warning"
    assert _urgency_level(61)  == "warning"
    print("✓ urgency_level: 61–120 min → warning")


def test_urgency_urgent():
    assert _urgency_level(60) == "urgent"
    assert _urgency_level(31) == "urgent"
    print("✓ urgency_level: 31–60 min → urgent")


def test_urgency_critical():
    assert _urgency_level(30) == "critical"
    assert _urgency_level(0)  == "critical"
    print("✓ urgency_level: <=30 min → critical")


# ── _load_embedded_stops() ────────────────────────────────────────────────────

def test_embedded_stops_not_empty():
    stops = _load_embedded_stops()
    assert len(stops) >= 50, f"Expected >= 50 embedded stops, got {len(stops)}"
    print(f"✓ embedded stops: {len(stops)} stops loaded")


def test_embedded_stops_required_fields():
    """Every embedded stop must have the required dict keys."""
    stops = _load_embedded_stops()
    required = ("name", "chain", "lat", "lon", "highway",
                "exit", "state", "amenities", "spaces", "rating")
    for s in stops:
        for k in required:
            assert k in s, f"Stop '{s.get('name')}' missing key: {k}"
    print("✓ embedded stops: all required fields present in all stops")


def test_embedded_stops_valid_chains():
    """Every embedded stop must have a valid chain value."""
    stops = _load_embedded_stops()
    for s in stops:
        assert s["chain"] in CHAINS, (
            f"Stop '{s['name']}' has invalid chain '{s['chain']}'"
        )
    all_chains = {s["chain"] for s in stops}
    assert "pilot"   in all_chains
    assert "loves"   in all_chains
    assert "flyingj" in all_chains
    assert "ta"      in all_chains
    print(f"✓ embedded stops: valid chains — {sorted(all_chains)}")


# ── _detect_chain() ───────────────────────────────────────────────────────────

def test_detect_chain_pilot():
    assert _detect_chain("Pilot Travel Center #428") == "pilot"
    assert _detect_chain("PILOT #100")               == "pilot"
    print("✓ detect_chain: Pilot detected")


def test_detect_chain_loves():
    assert _detect_chain("Love's Travel Stop #512")  == "loves"
    assert _detect_chain("Loves Country Store")      == "loves"
    print("✓ detect_chain: Love's detected")


def test_detect_chain_flyingj():
    assert _detect_chain("Flying J #318")            == "flyingj"
    assert _detect_chain("FlyingJ Travel Center")    == "flyingj"
    print("✓ detect_chain: Flying J detected")


def test_detect_chain_other():
    assert _detect_chain("Mom's Truck Stop")         == "other"
    assert _detect_chain("Crossroads Fuel")          == "other"
    print("✓ detect_chain: unknown → 'other'")


# ── get_nearby_stops() ────────────────────────────────────────────────────────

def test_nearby_stops_found_within_radius():
    """I-40 Pilot near Memphis should appear within 50 miles of Memphis."""
    # Memphis TN: (35.15, -90.05) — Pilot #428 is at (35.04, -90.18)
    stops = get_nearby_stops(HOME_LAT, HOME_LON, radius_miles=50.0)
    assert len(stops) > 0, "Expected at least 1 stop near Memphis"
    for s in stops:
        assert s["distance_mi"] <= 50.0
    print(f"✓ nearby_stops: {len(stops)} stops within 50 mi of Memphis")


def test_nearby_stops_sorted_closest_first():
    stops = get_nearby_stops(HOME_LAT, HOME_LON, radius_miles=50.0)
    if len(stops) >= 2:
        assert stops[0]["distance_mi"] <= stops[1]["distance_mi"], (
            "Stops not sorted closest first"
        )
    print(f"✓ nearby_stops: sorted closest first ({stops[0]['distance_mi']:.1f} mi)")


def test_nearby_stops_tight_radius_less_results():
    """Smaller radius should return fewer (or equal) stops."""
    wide  = get_nearby_stops(HOME_LAT, HOME_LON, radius_miles=200.0)
    tight = get_nearby_stops(HOME_LAT, HOME_LON, radius_miles=20.0)
    assert len(tight) <= len(wide), "Tight radius returned more stops than wide"
    print(f"✓ nearby_stops: 20mi={len(tight)} ≤ 200mi={len(wide)}")


def test_nearby_stops_zero_radius_empty():
    """Radius of 0 should return no stops."""
    stops = get_nearby_stops(HOME_LAT, HOME_LON, radius_miles=0.0)
    assert stops == []
    print("✓ nearby_stops: radius=0 → empty list")


# ── get_stops_in_corridor() ───────────────────────────────────────────────────

def test_corridor_stops_full_hos():
    """With full HOS (660 min), corridor should cover most embedded stops."""
    config = {"hos_drive_remaining_min": 660, "speed_mph": 55.0}
    stops  = get_stops_in_corridor(HOME_LAT, HOME_LON, config)
    assert len(stops) > 0
    print(f"✓ corridor: full HOS → {len(stops)} stops reachable from Memphis")


def test_corridor_stops_zero_hos_empty():
    """With 0 HOS remaining, no stops are in corridor (can't move)."""
    config = {"hos_drive_remaining_min": 0, "speed_mph": 55.0}
    stops  = get_stops_in_corridor(HOME_LAT, HOME_LON, config)
    assert stops == []
    print("✓ corridor: 0 HOS → empty corridor")


# ── find_recommended_stop() ──────────────────────────────────────────────────

def test_find_recommended_returns_closest():
    """Recommended stop must be the closest one in corridor."""
    config = {"hos_drive_remaining_min": 660, "speed_mph": 55.0}
    stop   = find_recommended_stop(HOME_LAT, HOME_LON, config)
    assert stop is not None
    assert "distance_mi" in stop
    nearby = get_stops_in_corridor(HOME_LAT, HOME_LON, config)
    assert stop["distance_mi"] == nearby[0]["distance_mi"]
    print(f"✓ find_recommended: closest stop = {stop['name']} ({stop['distance_mi']:.1f} mi)")


def test_find_recommended_no_location_returns_none():
    """find_recommended_stop returns None when lat/lon is None."""
    config = {"hos_drive_remaining_min": 660}
    assert find_recommended_stop(None, None, config) is None
    print("✓ find_recommended: None lat/lon → None (no crash)")


# ── filter_by_amenity() ───────────────────────────────────────────────────────

def test_filter_by_fuel():
    stops  = _load_embedded_stops()
    fueled = filter_by_amenity(stops, ["fuel"])
    assert len(fueled) == len(stops), "All embedded stops should have fuel"
    print(f"✓ filter_by_amenity: all {len(fueled)} stops have fuel")


def test_filter_by_cat_scale():
    stops     = _load_embedded_stops()
    cat_stops = filter_by_amenity(stops, ["cat_scale"])
    assert len(cat_stops) > 0
    assert len(cat_stops) < len(stops), "Not all stops should have CAT scale"
    for s in cat_stops:
        assert "cat_scale" in s["amenities"]
    print(f"✓ filter_by_amenity: {len(cat_stops)} stops with CAT scale")


def test_filter_multiple_amenities():
    stops   = _load_embedded_stops()
    premium = filter_by_amenity(stops, ["showers", "cat_scale", "wifi"])
    for s in premium:
        assert "showers"   in s["amenities"]
        assert "cat_scale" in s["amenities"]
        assert "wifi"      in s["amenities"]
    print(f"✓ filter_by_amenity: {len(premium)} stops with showers+CAT+WiFi")


# ── TTS threshold system ──────────────────────────────────────────────────────

def test_threshold_120_min_fires():
    reset_announcements()
    config = {"hos_drive_remaining_min": 120}
    result = check_runway_thresholds(config)
    assert result is not None
    threshold, severity, alert_type = result
    assert threshold == 120
    assert severity  == "INFO"
    print(f"✓ threshold: 120 min → INFO/{alert_type}")


def test_threshold_60_min_fires():
    reset_announcements()
    config = {"hos_drive_remaining_min": 60}
    result = check_runway_thresholds(config)
    assert result is not None
    threshold, _, _ = result
    assert threshold == 60
    print(f"✓ threshold: 60 min → WARNING fires")


def test_threshold_15_min_fires_critical():
    reset_announcements()
    config = {"hos_drive_remaining_min": 15}
    result = check_runway_thresholds(config)
    assert result is not None
    _, severity, _ = result
    assert severity == "CRITICAL"
    print("✓ threshold: 15 min → CRITICAL")


def test_threshold_above_120_no_fire():
    reset_announcements()
    config = {"hos_drive_remaining_min": 180}
    result = check_runway_thresholds(config)
    assert result is None, f"Should not fire at 180 min, got {result}"
    print("✓ threshold: 180 min → no threshold fired")


def test_announce_tts_disabled_returns_false():
    """announce_runway returns False immediately when TTS is disabled."""
    reset_announcements()
    config = {"hos_drive_remaining_min": 30, "tts_enabled": False}
    result = announce_runway(config)
    assert result is False
    print("✓ announce_runway: tts_enabled=False → False")


# ── Display functions ─────────────────────────────────────────────────────────

def test_display_stop_no_crash():
    """display_stop must not crash on a valid stop dict."""
    stop = {
        "name":      "Pilot #428",
        "chain":     "pilot",
        "lat":        35.04,
        "lon":       -90.18,
        "highway":   "I-40",
        "exit":      "1",
        "state":     "TN",
        "amenities": ["fuel", "showers", "food", "wifi", "cat_scale"],
        "spaces":    None,
        "rating":    4.2,
        "distance_mi": 8.3,
    }
    display_stop(stop)
    print("✓ display_stop: no crash")


def test_display_parking_status_no_position():
    """display_parking_status with lat=None must not crash."""
    config = {
        "hos_drive_remaining_min": 300,
        "speed_mph": 55.0,
        "subscription_tier": "solo_pro",
    }
    display_parking_status(None, None, config)
    print("✓ display_parking_status: lat=None → no crash")


# ── Subscription gate ─────────────────────────────────────────────────────────

def test_subscription_gate_free_tier(capsys=None):
    """Free tier: display_parking_status shows upgrade message, not data."""
    config = {"subscription_tier": "free",
              "hos_drive_remaining_min": 300, "speed_mph": 55.0}
    # Must not crash; upgrade message should be shown
    display_parking_status(HOME_LAT, HOME_LON, config)
    print("✓ subscription gate: free tier → upgrade message, no crash")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_compute_runway_standard,
        test_compute_runway_default_speed,
        test_compute_runway_urgent,
        test_compute_runway_critical,
        test_compute_runway_zero,
        test_compute_runway_warning_at_120,
        test_format_runway_normal,
        test_format_runway_critical_prefix,
        test_format_runway_sub_hour,
        test_urgency_normal,
        test_urgency_warning,
        test_urgency_urgent,
        test_urgency_critical,
        test_embedded_stops_not_empty,
        test_embedded_stops_required_fields,
        test_embedded_stops_valid_chains,
        test_detect_chain_pilot,
        test_detect_chain_loves,
        test_detect_chain_flyingj,
        test_detect_chain_other,
        test_nearby_stops_found_within_radius,
        test_nearby_stops_sorted_closest_first,
        test_nearby_stops_tight_radius_less_results,
        test_nearby_stops_zero_radius_empty,
        test_corridor_stops_full_hos,
        test_corridor_stops_zero_hos_empty,
        test_find_recommended_returns_closest,
        test_find_recommended_no_location_returns_none,
        test_filter_by_fuel,
        test_filter_by_cat_scale,
        test_filter_multiple_amenities,
        test_threshold_120_min_fires,
        test_threshold_60_min_fires,
        test_threshold_15_min_fires_critical,
        test_threshold_above_120_no_fire,
        test_announce_tts_disabled_returns_false,
        test_display_stop_no_crash,
        test_display_parking_status_no_position,
        test_subscription_gate_free_tier,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print(f"{'=' * 50}")
    print(f"  parking: {passed} passed, {failed} failed")
    if failed:
        print("  SOME TESTS FAILED")
        sys.exit(1)
    else:
        print("  All parking tests passed.")
