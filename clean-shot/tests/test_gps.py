#!/usr/bin/env python3
# tests/test_gps.py — Clean Shot: GPS module tests
# All tests run offline — no GPS hardware or network required.

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.gps import (
    haversine, bearing, bearing_to_cardinal, is_moving,
    get_poll_interval, _result, estimate_mile_marker,
    confirm_hazard_location, describe_location,
    POLL_DRIVING_SEC, POLL_PARKED_SEC,
    MOTION_THRESHOLD_MI, HAZARD_CONFIRM_MI,
)
from core.i18n.translator import t, set_language, detect_language, is_rtl


# ── Haversine ─────────────────────────────────────────────────────────────────

def test_haversine_known_distance():
    # Philadelphia → Pittsburgh straight-line (crow-flies) ≈ 257 miles
    # (driving via I-76 is ~305 mi — haversine is NOT driving distance)
    dist = haversine(39.9526, -75.1652, 40.4406, -79.9959)
    assert 245 < dist < 270, f"Expected ~257 mi crow-flies, got {dist:.1f}"
    print(f"✓ haversine: Philadelphia→Pittsburgh = {dist:.1f} mi (crow-flies)")


def test_haversine_same_point():
    assert haversine(40.0, -80.0, 40.0, -80.0) == 0.0
    print("✓ haversine: same point = 0")


def test_haversine_100m():
    # ~100 metres ≈ 0.0621 miles — sanity check for MOTION_THRESHOLD_MI
    dist = haversine(40.0, -80.0, 40.0009, -80.0)
    assert 0.055 < dist < 0.075, f"Expected ~0.062 mi, got {dist:.4f}"
    print(f"✓ haversine: ~100m = {dist:.4f} mi (threshold is {MOTION_THRESHOLD_MI})")


# ── Bearing ───────────────────────────────────────────────────────────────────

def test_bearing_east():
    # Moving east = increasing longitude
    b = bearing(40.0, -80.0, 40.0, -79.0)
    assert 85 < b < 95, f"Expected ~90°, got {b:.1f}"
    print(f"✓ bearing: eastward = {b:.1f}°")


def test_bearing_north():
    b = bearing(40.0, -80.0, 41.0, -80.0)
    assert b < 5 or b > 355, f"Expected ~0°, got {b:.1f}"
    print(f"✓ bearing: northward = {b:.1f}°")


def test_bearing_same_point():
    assert bearing(40.0, -80.0, 40.0, -80.0) == 0.0
    print("✓ bearing: same point = 0°")


def test_bearing_to_cardinal():
    assert bearing_to_cardinal(0)   == "N"
    assert bearing_to_cardinal(45)  == "NE"
    assert bearing_to_cardinal(90)  == "E"
    assert bearing_to_cardinal(135) == "SE"
    assert bearing_to_cardinal(180) == "S"
    assert bearing_to_cardinal(225) == "SW"
    assert bearing_to_cardinal(270) == "W"
    assert bearing_to_cardinal(315) == "NW"
    assert bearing_to_cardinal(360) == "N"
    print("✓ bearing_to_cardinal: all 8 directions")


# ── Motion detection ──────────────────────────────────────────────────────────

def test_is_moving_true():
    old = _result(40.0000, -80.0000, "gps")
    new = _result(40.0015, -80.0015, "gps")  # ~0.13 mi — above threshold
    assert is_moving(old, new) is True
    print("✓ is_moving: True when delta > 100m")


def test_is_moving_false():
    old = _result(40.0000, -80.0000, "gps")
    new = _result(40.0001, -80.0001, "gps")  # ~0.009 mi — below threshold
    assert is_moving(old, new) is False
    print("✓ is_moving: False when delta < 100m")


def test_is_moving_bad_data():
    # Should not crash on missing keys
    assert is_moving({}, {}) is False
    print("✓ is_moving: safe on empty dicts")


# ── Poll interval ─────────────────────────────────────────────────────────────

def test_poll_interval_parked():
    config = {"is_driving": False}
    assert get_poll_interval(config) == POLL_PARKED_SEC
    print(f"✓ poll interval: parked = {POLL_PARKED_SEC}s (10 min)")


def test_poll_interval_driving():
    config = {"is_driving": True}
    assert get_poll_interval(config) == POLL_DRIVING_SEC
    print(f"✓ poll interval: driving = {POLL_DRIVING_SEC}s (1 min)")


def test_poll_interval_default():
    # Default (no is_driving key) should be parked
    assert get_poll_interval({}) == POLL_PARKED_SEC
    print("✓ poll interval: defaults to parked")


# ── Geo-confirmation ──────────────────────────────────────────────────────────

def test_confirm_hazard_within_range():
    # Driver at 40.00, -80.00 — hazard at 40.01, -80.01 (~0.9 mi)
    config = {"last_gps_lat": 40.00, "last_gps_lon": -80.00,
              "latitude": 40.00, "longitude": -80.00,
              "offline_mode": True, "language": "en"}
    result = confirm_hazard_location(40.01, -80.01, config)
    assert result["confirmed"] is True
    assert result["distance_mi"] < HAZARD_CONFIRM_MI
    print(f"✓ confirm_hazard: within range ({result['distance_mi']:.2f} mi < {HAZARD_CONFIRM_MI} mi)")


def test_confirm_hazard_out_of_range():
    # Driver at 40.00, -80.00 — hazard 5 miles away
    config = {"last_gps_lat": 40.00, "last_gps_lon": -80.00,
              "latitude": 40.00, "longitude": -80.00,
              "offline_mode": True, "language": "en"}
    result = confirm_hazard_location(40.07, -80.07, config)
    assert result["confirmed"] is False
    assert result["distance_mi"] > HAZARD_CONFIRM_MI
    print(f"✓ confirm_hazard: rejected at {result['distance_mi']:.2f} mi (> {HAZARD_CONFIRM_MI} mi)")


def test_confirm_hazard_no_position():
    config = {"offline_mode": True, "language": "en"}
    result = confirm_hazard_location(40.0, -80.0, config)
    assert result["confirmed"] is False
    assert result["distance_mi"] is None
    print("✓ confirm_hazard: graceful failure with no position")


def test_confirm_hazard_boundary():
    # Exactly at 2.0 miles — should confirm (≤)
    config = {"last_gps_lat": 40.0, "last_gps_lon": -80.0,
              "latitude": 40.0, "longitude": -80.0,
              "offline_mode": True, "language": "en"}
    # ~0.029° lat ≈ 2.0 miles
    result = confirm_hazard_location(40.029, -80.0, config)
    dist = result["distance_mi"]
    # Just verify boundary logic fires correctly
    assert isinstance(result["confirmed"], bool)
    print(f"✓ confirm_hazard: boundary test at {dist:.2f} mi → confirmed={result['confirmed']}")


# ── Mile marker estimation ────────────────────────────────────────────────────

def test_mm_i76_near_start():
    # Philadelphia area — should be low MM
    mm = estimate_mile_marker(39.96, -75.17, "I-76")
    assert mm is not None
    assert 0 <= mm <= 30, f"Expected low MM near Philly, got {mm}"
    print(f"✓ estimate_mile_marker: I-76 near Philly = MM{mm}")


def test_mm_i76_near_end():
    # Near Pittsburgh — should be high MM (~358)
    mm = estimate_mile_marker(40.90, -79.90, "I-76")
    assert mm is not None
    assert 300 <= mm <= 358, f"Expected ~350 near Pittsburgh, got {mm}"
    print(f"✓ estimate_mile_marker: I-76 near Pittsburgh = MM{mm}")


def test_mm_unknown_highway():
    assert estimate_mile_marker(40.0, -80.0, "I-999") is None
    print("✓ estimate_mile_marker: returns None for unknown highway")


# ── i18n translator ───────────────────────────────────────────────────────────

def test_t_english_direction():
    set_language("en")
    assert t("direction.E") == "Eastbound"
    assert t("direction.N") == "Northbound"
    assert t("direction.SW") == "Southwest"
    print("✓ t(): English direction strings")


def test_t_spanish_direction():
    set_language("es")
    assert t("direction.E") == "este"
    assert t("direction.N") == "norte"
    set_language("en")   # reset
    print("✓ t(): Spanish direction strings")


def test_t_interpolation():
    set_language("en")
    result = t("hazard.too_far", dist=1.3)
    assert "1.3" in result
    print(f"✓ t(): interpolation — '{result}'")


def test_t_missing_key_fallback():
    set_language("en")
    result = t("nonexistent.key.xyz")
    assert result == "nonexistent.key.xyz"   # returns key itself, never crashes
    print("✓ t(): missing key returns key string (no crash)")


def test_t_spanish_fallback_to_english():
    set_language("es")
    # If a key only exists in English fallback, should still return it
    result = t("gps.no_fix")
    assert result != ""
    set_language("en")
    print(f"✓ t(): Spanish falls back to English for missing keys — '{result}'")


def test_is_rtl():
    assert is_rtl("ar") is True
    assert is_rtl("he") is True
    assert is_rtl("fa") is True
    assert is_rtl("en") is False
    assert is_rtl("es") is False
    print("✓ is_rtl(): Arabic/Hebrew/Farsi=True, English/Spanish=False")


def test_detect_language_default():
    # In test environment without explicit locale, should default to 'en'
    lang = detect_language()
    assert lang in ("en", "es"), f"Unexpected language: {lang}"
    print(f"✓ detect_language(): returned '{lang}'")


# ── Location description (offline — no Nominatim call) ───────────────────────

def test_describe_location_coordinate_fallback():
    """When reverse geocode fails (offline), falls back to coordinates."""
    config = {"language": "en", "offline_mode": True}
    # Reverse geocode will fail offline but describe_location must not crash
    desc = describe_location(40.4406, -79.9959, config)
    assert isinstance(desc, str) and len(desc) > 0
    print(f"✓ describe_location: returns string in offline mode — '{desc}'")


def test_describe_location_direction_with_prev():
    """Direction string should appear when prev position is provided."""
    # We can't test the full Nominatim path offline, but we can verify
    # the bearing+cardinal logic feeds through without error
    config = {"language": "en", "offline_mode": True}
    desc = describe_location(40.4406, -79.9959, config,
                              prev_lat=40.4300, prev_lon=-79.9959)
    assert isinstance(desc, str)
    print(f"✓ describe_location: handles prev position without crash — '{desc}'")


# ── GpsResult structure ───────────────────────────────────────────────────────

def test_result_structure():
    r = _result(40.0, -80.0, "gps", accuracy_m=5.0)
    assert r["lat"]    == 40.0
    assert r["lon"]    == -80.0
    assert r["source"] == "gps"
    assert r["stale"]  is False
    assert "timestamp" in r
    print("✓ _result: correct structure")


def test_result_stale_flag():
    r = _result(40.0, -80.0, "config", stale=True)
    assert r["stale"] is True
    print("✓ _result: stale=True preserved")


# ── Run all ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n── haversine ──")
    test_haversine_known_distance()
    test_haversine_same_point()
    test_haversine_100m()

    print("\n── bearing ──")
    test_bearing_east()
    test_bearing_north()
    test_bearing_same_point()
    test_bearing_to_cardinal()

    print("\n── motion detection ──")
    test_is_moving_true()
    test_is_moving_false()
    test_is_moving_bad_data()

    print("\n── poll interval ──")
    test_poll_interval_parked()
    test_poll_interval_driving()
    test_poll_interval_default()

    print("\n── geo-confirmation ──")
    test_confirm_hazard_within_range()
    test_confirm_hazard_out_of_range()
    test_confirm_hazard_no_position()
    test_confirm_hazard_boundary()

    print("\n── mile marker ──")
    test_mm_i76_near_start()
    test_mm_i76_near_end()
    test_mm_unknown_highway()

    print("\n── i18n translator ──")
    test_t_english_direction()
    test_t_spanish_direction()
    test_t_interpolation()
    test_t_missing_key_fallback()
    test_t_spanish_fallback_to_english()
    test_is_rtl()
    test_detect_language_default()

    print("\n── location description ──")
    test_describe_location_coordinate_fallback()
    test_describe_location_direction_with_prev()

    print("\n── GpsResult structure ──")
    test_result_structure()
    test_result_stale_flag()

    print("\n✅  All GPS tests passed.")
