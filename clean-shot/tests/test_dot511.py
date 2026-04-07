#!/usr/bin/env python3
# tests/test_dot511.py — Clean Shot: DOT/511 module tests
#
# Covers:
#   NWS event → incident type mapping      (4 tests)
#   NWS severity mapping                   (4 tests)
#   Chain requirement detection            (4 tests)
#   Highway extraction                     (4 tests)
#   Direction extraction                   (2 tests)
#   NWS feature parsing                    (5 tests)
#   filter_truck_relevant                  (4 tests)
#   State code coverage                    (3 tests)
#   State bounding box / lat_lon_to_state  (3 tests)
#   Display output                         (2 tests)
#   TTS routing                            (1 test)
# Total: 36 tests (all offline — no network, no audio)

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.dot511 import (
    STATE_CODES,
    STATE_FEEDS,
    _STATE_BOUNDS,
    _has_chain_requirement,
    _extract_highway,
    _extract_direction,
    _nws_event_to_type,
    _nws_severity,
    _parse_nws_feature,
    _iso_to_unix,
    _lat_lon_to_state,
    _truncate_desc,
    parse_nws_features,
    filter_truck_relevant,
    speak_dot511_alerts,
    display_dot511,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_nws_feature(event="Winter Storm Warning", headline="",
                      description="", severity="Severe",
                      urgency="Expected", expires=None):
    """Build a minimal NWS GeoJSON feature dict for testing."""
    return {
        "properties": {
            "event":       event,
            "headline":    headline,
            "description": description,
            "severity":    severity,
            "urgency":     urgency,
            "expires":     expires,
        }
    }


def _make_incident(itype="weather_advisory", severity="medium",
                   highway=None, description="Test advisory", truck_only=False):
    return {
        "type":        itype,
        "severity":    severity,
        "highway":     highway,
        "direction":   "unknown",
        "description": description,
        "source":      "nws",
        "expires":     None,
        "truck_only":  truck_only,
    }


# ── NWS event → incident type ─────────────────────────────────────────────────

def test_nws_event_winter_storm():
    assert _nws_event_to_type("Winter Storm Warning") == "weather_advisory"
    assert _nws_event_to_type("Blizzard Warning")     == "weather_advisory"
    assert _nws_event_to_type("Ice Storm Warning")    == "weather_advisory"
    print("✓ nws_event_to_type: winter/blizzard/ice → weather_advisory")


def test_nws_event_fog_wind_flood():
    assert _nws_event_to_type("Dense Fog Advisory")  == "weather_advisory"
    assert _nws_event_to_type("High Wind Warning")   == "weather_advisory"
    assert _nws_event_to_type("Flash Flood Warning") == "weather_advisory"
    print("✓ nws_event_to_type: fog/wind/flood → weather_advisory")


def test_nws_event_closure():
    assert _nws_event_to_type("Road Closure") == "closure"
    print("✓ nws_event_to_type: Road Closure → closure")


def test_nws_event_unknown_defaults():
    """Unknown NWS events default to weather_advisory, not None."""
    assert _nws_event_to_type("Space Weather Advisory") == "weather_advisory"
    assert _nws_event_to_type("Something New")          == "weather_advisory"
    print("✓ nws_event_to_type: unknown → weather_advisory (safe default)")


# ── NWS severity mapping ──────────────────────────────────────────────────────

def test_severity_extreme_is_critical():
    assert _nws_severity("Extreme", "Immediate") == "critical"
    assert _nws_severity("Extreme", "Expected")  == "critical"
    print("✓ nws_severity: Extreme → critical")


def test_severity_severe_is_high():
    assert _nws_severity("Severe", "Immediate") == "high"
    assert _nws_severity("Severe", "Expected")  == "high"
    print("✓ nws_severity: Severe → high")


def test_severity_moderate_urgency_split():
    assert _nws_severity("Moderate", "Immediate") == "medium"
    assert _nws_severity("Moderate", "Expected")  == "low"
    assert _nws_severity("Moderate", "Future")    == "low"
    print("✓ nws_severity: Moderate — Immediate=medium, Expected/Future=low")


def test_severity_unknown_is_low():
    assert _nws_severity("Minor",   "Unknown") == "low"
    assert _nws_severity("Unknown", "Unknown") == "low"
    print("✓ nws_severity: Minor/Unknown → low")


# ── Chain requirement detection ───────────────────────────────────────────────

def test_chain_detected_basic():
    assert _has_chain_requirement("chains required on I-70 westbound") is True
    print("✓ chain detection: 'chains required' detected")


def test_chain_detected_traction_law():
    assert _has_chain_requirement("Traction law in effect for commercial vehicles") is True
    assert _has_chain_requirement("no bare tires allowed on highway") is True
    print("✓ chain detection: traction law / no bare tires detected")


def test_chain_not_present():
    assert _has_chain_requirement("slippery roads, reduced visibility") is False
    assert _has_chain_requirement("Winter Storm Warning issued until Monday") is False
    print("✓ chain detection: no false positives on slippery/winter text")


def test_chain_case_insensitive():
    assert _has_chain_requirement("CHAIN CONTROL in effect") is True
    assert _has_chain_requirement("Chain Law enforced") is True
    print("✓ chain detection: case-insensitive")


# ── Highway extraction ────────────────────────────────────────────────────────

def test_extract_highway_interstate():
    assert _extract_highway("Ice on I-70 near Vail Pass")      == "I-70"
    assert _extract_highway("Chains required on I-15 north")   == "I-15"
    assert _extract_highway("Closure on I-90W near Spokane")   == "I-90W"
    print("✓ extract_highway: I-XX interstates extracted")


def test_extract_highway_us_route():
    assert _extract_highway("Flooding on US-40 near Granby")   == "US-40"
    assert _extract_highway("Road closed on US 6")             == "US-6"
    print("✓ extract_highway: US routes extracted and normalized")


def test_extract_highway_named():
    assert _extract_highway("Highway 285 is closed")           == "HIGHWAY-285"
    assert _extract_highway("Hwy 9 has chain requirements")    == "HWY-9"
    print("✓ extract_highway: named highways extracted")


def test_extract_highway_not_found():
    assert _extract_highway("Heavy snow in Summit County") is None
    assert _extract_highway("General road conditions")     is None
    assert _extract_highway("")                            is None
    print("✓ extract_highway: returns None when no highway in text")


# ── Direction extraction ──────────────────────────────────────────────────────

def test_extract_direction_found():
    assert _extract_direction("I-70 westbound near Glenwood Canyon")   == "westbound"
    assert _extract_direction("Chains required northbound I-15")       == "northbound"
    assert _extract_direction("Both directions closed at summit")      == "both"
    print("✓ extract_direction: directions extracted correctly")


def test_extract_direction_not_found():
    assert _extract_direction("Winter Storm Warning for Summit County") == "unknown"
    assert _extract_direction("")                                       == "unknown"
    print("✓ extract_direction: returns 'unknown' when missing")


# ── NWS feature parsing ───────────────────────────────────────────────────────

def test_parse_nws_basic_incident():
    """Standard NWS feature should parse to a valid incident dict."""
    feat = _make_nws_feature(
        event="Winter Storm Warning",
        headline="Winter Storm Warning until Monday",
        severity="Severe", urgency="Expected",
    )
    inc = _parse_nws_feature(feat)
    assert inc is not None
    assert inc["type"]     == "weather_advisory"
    assert inc["severity"] == "high"
    assert inc["source"]   == "nws"
    print("✓ parse_nws_feature: basic winter storm → weather_advisory/high")


def test_parse_nws_chains_in_headline_upgrades_type():
    """Headline mentioning chains must set type to chains_required."""
    feat = _make_nws_feature(
        event="Winter Storm Warning",
        headline="Chains required on I-70 — Winter Storm Warning until Tuesday",
        severity="Severe", urgency="Immediate",
    )
    inc = _parse_nws_feature(feat)
    assert inc is not None
    assert inc["type"]    == "chains_required"
    assert inc["highway"] == "I-70"
    print("✓ parse_nws_feature: chain mention upgrades type, highway extracted")


def test_parse_nws_skips_marine_events():
    """Marine and beach events must be filtered out (None returned)."""
    for event in ("Special Marine Warning", "Rip Current Statement",
                  "Coastal Flood Advisory", "Tornado Warning"):
        feat = _make_nws_feature(event=event)
        assert _parse_nws_feature(feat) is None, f"{event} should return None"
    print("✓ parse_nws_feature: marine/tornado/beach events skipped")


def test_parse_nws_description_truncated():
    """Long headline must be truncated to <= 100 chars."""
    long_headline = "A " + "very " * 30 + "long advisory headline"
    feat = _make_nws_feature(headline=long_headline)
    inc  = _parse_nws_feature(feat)
    assert inc is not None
    assert len(inc["description"]) <= 101  # 100 + possible ellipsis char
    print(f"✓ parse_nws_feature: description truncated ({len(inc['description'])} chars)")


def test_parse_nws_required_keys():
    """Every parsed incident must have all required keys."""
    feat = _make_nws_feature()
    inc  = _parse_nws_feature(feat)
    assert inc is not None
    for key in ("type", "severity", "highway", "direction",
                "description", "source", "expires", "truck_only"):
        assert key in inc, f"Missing key: {key}"
    print("✓ parse_nws_feature: all required keys present")


# ── parse_nws_features (list) ─────────────────────────────────────────────────

def test_parse_nws_features_empty():
    assert parse_nws_features([]) == []
    print("✓ parse_nws_features: empty input → empty list")


# ── filter_truck_relevant ─────────────────────────────────────────────────────

def test_filter_keeps_chains_and_closures():
    """chains_required and closure always pass through regardless of severity."""
    incidents = [
        _make_incident("chains_required", "low"),
        _make_incident("closure",         "low"),
    ]
    result = filter_truck_relevant(incidents)
    assert len(result) == 2
    print("✓ filter_truck_relevant: chains/closure always kept")


def test_filter_keeps_high_severity_advisory():
    """High-severity weather advisory without highway mention is still kept."""
    incidents = [_make_incident("weather_advisory", "high")]
    result = filter_truck_relevant(incidents)
    assert len(result) == 1
    print("✓ filter_truck_relevant: high severity advisory kept")


def test_filter_empty_input():
    assert filter_truck_relevant([]) == []
    print("✓ filter_truck_relevant: empty input → empty list")


def test_filter_passes_incidents_through():
    """Incident type always passes through."""
    incidents = [_make_incident("incident", "medium")]
    result = filter_truck_relevant(incidents)
    assert len(result) == 1
    print("✓ filter_truck_relevant: incident type passes through")


# ── State code coverage ───────────────────────────────────────────────────────

def test_all_50_states_plus_dc_in_state_codes():
    assert len(STATE_CODES) == 51, f"Expected 51 (50+DC), got {len(STATE_CODES)}"
    assert "TX" in STATE_CODES
    assert "AK" in STATE_CODES
    assert "HI" in STATE_CODES
    assert "DC" in STATE_CODES
    print(f"✓ STATE_CODES: all 51 present (50 states + DC)")


def test_state_feeds_has_all_state_codes():
    """Every state in STATE_CODES must have an entry in STATE_FEEDS."""
    missing = [s for s in STATE_CODES if s not in STATE_FEEDS]
    assert not missing, f"Missing from STATE_FEEDS: {missing}"
    print("✓ STATE_FEEDS: all 51 state codes present")


def test_state_feeds_values_are_none_or_string():
    """All STATE_FEEDS values must be None (stub) or a string URL (active feed)."""
    bad = {k: v for k, v in STATE_FEEDS.items()
           if v is not None and not isinstance(v, str)}
    assert not bad, f"Invalid STATE_FEEDS values: {bad}"
    print("✓ STATE_FEEDS: all values are None or string")


# ── State bounding box / lat_lon_to_state ────────────────────────────────────

def test_lat_lon_to_state_texas():
    state = _lat_lon_to_state(30.0, -97.5)
    assert state == "TX", f"Expected TX, got {state}"
    print(f"✓ lat_lon_to_state: Austin TX → {state}")


def test_lat_lon_to_state_colorado():
    state = _lat_lon_to_state(39.5, -105.0)
    assert state == "CO", f"Expected CO, got {state}"
    print(f"✓ lat_lon_to_state: Denver CO → {state}")


def test_lat_lon_to_state_outside_us():
    state = _lat_lon_to_state(0.0, 0.0)    # Gulf of Guinea
    assert state is None
    state2 = _lat_lon_to_state(55.0, -3.5) # Scotland
    assert state2 is None
    print("✓ lat_lon_to_state: outside US → None")


# ── Utility helpers ───────────────────────────────────────────────────────────

def test_truncate_desc_short_unchanged():
    s = "Short text"
    assert _truncate_desc(s, 100) == s
    print("✓ truncate_desc: short text unchanged")


def test_truncate_desc_long_trimmed():
    s = "word " * 30
    result = _truncate_desc(s, 100)
    assert len(result) <= 101
    print(f"✓ truncate_desc: long text trimmed to {len(result)} chars")


def test_iso_to_unix_valid():
    ts = _iso_to_unix("2024-12-15T18:00:00+00:00")
    assert isinstance(ts, int) and ts > 0
    print(f"✓ iso_to_unix: valid ISO → {ts}")


def test_iso_to_unix_none_input():
    assert _iso_to_unix(None) is None
    assert _iso_to_unix("")   is None
    print("✓ iso_to_unix: None/empty → None (no crash)")


# ── Display ───────────────────────────────────────────────────────────────────

def test_display_empty_no_crash(capsys=None):
    """display_dot511 with empty list must not crash."""
    display_dot511([], config={})
    print("✓ display_dot511: empty list → no crash")


def test_display_single_incident_no_crash():
    """display_dot511 with one incident must not crash."""
    incidents = [_make_incident("chains_required", "high",
                                highway="I-70", description="Chains on I-70")]
    display_dot511(incidents, config={})
    print("✓ display_dot511: single incident — no crash")


# ── TTS ───────────────────────────────────────────────────────────────────────

def test_speak_dot511_tts_disabled():
    incidents = [_make_incident("chains_required", "critical")]
    spoken = speak_dot511_alerts(incidents, config={"tts_enabled": False})
    assert spoken == 0
    print("✓ speak_dot511_alerts: tts_enabled=False → 0 spoken")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        # NWS event type
        test_nws_event_winter_storm,
        test_nws_event_fog_wind_flood,
        test_nws_event_closure,
        test_nws_event_unknown_defaults,
        # Severity
        test_severity_extreme_is_critical,
        test_severity_severe_is_high,
        test_severity_moderate_urgency_split,
        test_severity_unknown_is_low,
        # Chain detection
        test_chain_detected_basic,
        test_chain_detected_traction_law,
        test_chain_not_present,
        test_chain_case_insensitive,
        # Highway extraction
        test_extract_highway_interstate,
        test_extract_highway_us_route,
        test_extract_highway_named,
        test_extract_highway_not_found,
        # Direction
        test_extract_direction_found,
        test_extract_direction_not_found,
        # NWS parsing
        test_parse_nws_basic_incident,
        test_parse_nws_chains_in_headline_upgrades_type,
        test_parse_nws_skips_marine_events,
        test_parse_nws_description_truncated,
        test_parse_nws_required_keys,
        test_parse_nws_features_empty,
        # Filter
        test_filter_keeps_chains_and_closures,
        test_filter_keeps_high_severity_advisory,
        test_filter_empty_input,
        test_filter_passes_incidents_through,
        # State coverage
        test_all_50_states_plus_dc_in_state_codes,
        test_state_feeds_has_all_state_codes,
        test_state_feeds_values_are_none_or_string,
        # Bounding box
        test_lat_lon_to_state_texas,
        test_lat_lon_to_state_colorado,
        test_lat_lon_to_state_outside_us,
        # Utilities
        test_truncate_desc_short_unchanged,
        test_truncate_desc_long_trimmed,
        test_iso_to_unix_valid,
        test_iso_to_unix_none_input,
        # Display
        test_display_empty_no_crash,
        test_display_single_incident_no_crash,
        # TTS
        test_speak_dot511_tts_disabled,
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
    print(f"  dot511: {passed} passed, {failed} failed")
    if failed:
        print(f"  SOME TESTS FAILED")
        sys.exit(1)
    else:
        print(f"  All DOT/511 tests passed.")
