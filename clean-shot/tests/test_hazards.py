#!/usr/bin/env python3
# tests/test_hazards.py — Clean Shot: hazard module tests
#
# Covers:
#   claude/parser._parse_offline()          (3 tests — existing)
#   core/hazards data budget                (2 tests)
#   core/hazards report construction        (3 tests)
#   core/hazards submit_hazard              (4 tests)
#   core/hazards nearby filtering           (6 tests)
#   core/hazards expire_old_hazards         (3 tests)
#   core/hazards cluster_reports            (6 tests)
#   core/hazards type/severity mapping      (3 tests)
# Total: 30 tests

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core.hazards as hazards
from core.hazards import (
    CLUSTER_MIN_REPORTS,
    CLUSTER_RADIUS_MI,
    CLUSTER_WINDOW_MIN,
    MAX_HAZARD_AGE_H,
    _make_report,
    _serialize_report,
    cluster_reports,
    expire_old_hazards,
    get_nearby_hazards,
    hazard_to_alert_type,
    severity_to_tts,
    speak_nearby_hazards,
    submit_hazard,
    clear_local_store,
)
from claude.parser import _parse_offline


# ── Helpers ────────────────────────────────────────────────────────────────────

# Memphis TN (used as driver position in all tests)
HOME_LAT = 35.1495
HOME_LON = -90.0490

def _fresh_ts():
    """Unix timestamp 30 minutes ago — within any active window."""
    return int(time.time()) - 1800

def _old_ts():
    """Unix timestamp 5 hours ago — outside MAX_HAZARD_AGE_H."""
    return int(time.time()) - int(MAX_HAZARD_AGE_H * 3600 + 600)

def _recent_ts():
    """Unix timestamp 10 minutes ago — within cluster window."""
    return int(time.time()) - 600

def _outside_window_ts():
    """Unix timestamp just outside CLUSTER_WINDOW_MIN."""
    return int(time.time()) - int(CLUSTER_WINDOW_MIN * 60 + 60)

def _make_nearby_report(lat_offset=0.05, htype="black_ice", sev="medium",
                        ts=None, clr=False):
    """Return a minimal hazard dict as stored in the local cache."""
    return {
        "t":   htype,
        "lat": round(HOME_LAT + lat_offset, 4),
        "lon": HOME_LON,
        "ts":  ts if ts is not None else _fresh_ts(),
        "sev": sev,
        "dir": "unknown",
        "src": "community",
        "clr": clr,
        "note": "",
    }


# ── Existing parser tests (keep passing) ─────────────────────────────────────

def test_offline_parser_black_ice():
    result = _parse_offline("black ice on the interstate")
    assert result["type"] == "black_ice", f"Got {result['type']}"
    print("✓ offline parser: black_ice")


def test_offline_parser_fog():
    result = _parse_offline("heavy fog, can't see a thing")
    assert result["type"] == "fog"
    print("✓ offline parser: fog")


def test_offline_parser_fallback():
    result = _parse_offline("something weird on the road")
    assert result["type"] == "other"
    print("✓ offline parser: fallback to other")


# ── Data budget ────────────────────────────────────────────────────────────────

def test_report_under_200_bytes():
    """A typical report must be under the 200-byte network budget."""
    parsed = {"type": "black_ice", "severity": "high",
              "direction": "northbound", "cleared": False,
              "notes": "ice on bridge deck — slick"}
    report = _make_report(35.1495, -90.0490, parsed)
    serialized = _serialize_report(report)
    size = len(serialized.encode())
    assert size < 200, f"Report is {size} bytes — exceeds 200-byte budget"
    print(f"✓ data budget: {size} bytes (< 200)")


def test_report_long_note_trimmed_by_submit():
    """submit_hazard must trim the note until the report fits under 200 bytes."""
    clear_local_store()
    long_note = "x" * 200   # deliberately oversized
    submit_hazard(HOME_LAT, HOME_LON, hazard_type="debris",
                  description=long_note, config={})
    from core.hazards import _load_local_store
    reports = _load_local_store()
    assert reports, "No reports stored"
    serialized = _serialize_report(reports[-1])
    assert len(serialized.encode()) <= 200, (
        f"Report not trimmed: {len(serialized.encode())} bytes"
    )
    print("✓ data budget: long note trimmed by submit_hazard")


# ── Report construction ────────────────────────────────────────────────────────

def test_make_report_all_fields_present():
    """_make_report must include all required keys."""
    parsed = {"type": "fog", "severity": "medium", "direction": "both",
              "cleared": False, "notes": "thick"}
    r = _make_report(35.15, -90.05, parsed)
    for key in ("t", "lat", "lon", "ts", "sev", "dir", "src", "clr", "note"):
        assert key in r, f"Missing key: {key}"
    print("✓ make_report: all required fields present")


def test_make_report_timestamp_is_recent():
    """_make_report timestamp must be within 5 seconds of now."""
    parsed = {"type": "other", "severity": "low", "direction": "unknown",
              "cleared": False, "notes": ""}
    r = _make_report(35.0, -90.0, parsed)
    assert abs(r["ts"] - int(time.time())) <= 5
    print("✓ make_report: timestamp is recent")


def test_make_report_coordinates_rounded():
    """Lat/lon must be rounded to 4 decimal places."""
    parsed = {"type": "accident", "severity": "high", "direction": "unknown",
              "cleared": False, "notes": ""}
    r = _make_report(35.149512345, -90.049067890, parsed)
    assert r["lat"] == round(35.149512345, 4)
    assert r["lon"] == round(-90.049067890, 4)
    print("✓ make_report: coordinates rounded to 4dp")


# ── Submit hazard ──────────────────────────────────────────────────────────────

def test_submit_hazard_returns_true():
    """submit_hazard must return True on success."""
    clear_local_store()
    result = submit_hazard(HOME_LAT, HOME_LON, hazard_type="fog",
                           description="", config={})
    assert result is True
    print("✓ submit_hazard: returns True")


def test_submit_hazard_stores_report():
    """Submitted report must appear in the local store."""
    clear_local_store()
    submit_hazard(HOME_LAT, HOME_LON, hazard_type="black_ice",
                  description="", config={})
    from core.hazards import _load_local_store
    reports = _load_local_store()
    assert len(reports) == 1
    assert reports[0]["t"] == "black_ice"
    print("✓ submit_hazard: report stored locally")


def test_submit_hazard_explicit_type_overrides_parsed():
    """Explicit hazard_type must win over parsed type from description."""
    clear_local_store()
    submit_hazard(HOME_LAT, HOME_LON, hazard_type="flood",
                  description="there is some fog out here", config={})
    from core.hazards import _load_local_store
    r = _load_local_store()[-1]
    assert r["t"] == "flood", f"Expected flood, got {r['t']}"
    print("✓ submit_hazard: explicit type overrides description parse")


def test_submit_hazard_parses_description():
    """When no explicit type given, description is parsed for type."""
    clear_local_store()
    submit_hazard(HOME_LAT, HOME_LON, hazard_type="",
                  description="ice everywhere on the bridge", config={})
    from core.hazards import _load_local_store
    r = _load_local_store()[-1]
    assert r["t"] == "black_ice", f"Expected black_ice, got {r['t']}"
    print("✓ submit_hazard: description parsed for type")


# ── Nearby filtering ───────────────────────────────────────────────────────────

def test_nearby_within_radius_included():
    """Hazard ~3.5 miles away (0.05° lat ≈ 3.5 mi) should appear in 25mi radius."""
    clear_local_store()
    from core.hazards import _save_local_store
    _save_local_store([_make_nearby_report(lat_offset=0.05)])
    nearby = get_nearby_hazards(HOME_LAT, HOME_LON, radius_miles=25.0)
    assert len(nearby) == 1, f"Expected 1, got {len(nearby)}"
    print(f"✓ nearby: within radius included ({nearby[0]['distance_mi']:.1f} mi)")


def test_nearby_outside_radius_excluded():
    """Hazard ~35 miles away (0.5° lat ≈ 34 mi) must be excluded from 25mi radius."""
    clear_local_store()
    from core.hazards import _save_local_store
    _save_local_store([_make_nearby_report(lat_offset=0.50)])
    nearby = get_nearby_hazards(HOME_LAT, HOME_LON, radius_miles=25.0)
    assert len(nearby) == 0, f"Expected 0, got {len(nearby)}"
    print("✓ nearby: outside radius excluded")


def test_nearby_expired_excluded():
    """Hazard older than MAX_HAZARD_AGE_H must not appear."""
    clear_local_store()
    from core.hazards import _save_local_store
    _save_local_store([_make_nearby_report(lat_offset=0.05, ts=_old_ts())])
    nearby = get_nearby_hazards(HOME_LAT, HOME_LON, radius_miles=25.0)
    assert len(nearby) == 0, f"Expired hazard still returned: {nearby}"
    print("✓ nearby: expired report excluded")


def test_nearby_fresh_included():
    """Hazard 30 minutes old (well within 4h window) must appear."""
    clear_local_store()
    from core.hazards import _save_local_store
    _save_local_store([_make_nearby_report(lat_offset=0.05, ts=_fresh_ts())])
    nearby = get_nearby_hazards(HOME_LAT, HOME_LON, radius_miles=25.0)
    assert len(nearby) == 1
    print("✓ nearby: fresh report included")


def test_nearby_cleared_excluded():
    """Report marked clr=True must be excluded."""
    clear_local_store()
    from core.hazards import _save_local_store
    _save_local_store([_make_nearby_report(lat_offset=0.05, clr=True)])
    nearby = get_nearby_hazards(HOME_LAT, HOME_LON, radius_miles=25.0)
    assert len(nearby) == 0, "Cleared hazard should not appear"
    print("✓ nearby: cleared report excluded")


def test_nearby_sorted_closest_first():
    """Multiple hazards must be sorted by distance, closest first."""
    clear_local_store()
    from core.hazards import _save_local_store
    _save_local_store([
        _make_nearby_report(lat_offset=0.20),   # farther ~14 mi
        _make_nearby_report(lat_offset=0.05),   # closer  ~3.5 mi
    ])
    nearby = get_nearby_hazards(HOME_LAT, HOME_LON, radius_miles=25.0)
    assert len(nearby) == 2
    assert nearby[0]["distance_mi"] < nearby[1]["distance_mi"], (
        "Results not sorted closest-first"
    )
    print(f"✓ nearby: sorted closest first "
          f"({nearby[0]['distance_mi']:.1f} mi < {nearby[1]['distance_mi']:.1f} mi)")


# ── Expiry ────────────────────────────────────────────────────────────────────

def test_expire_removes_old():
    """expire_old_hazards must remove reports older than MAX_HAZARD_AGE_H."""
    reports = [_make_nearby_report(ts=_old_ts()),
               _make_nearby_report(ts=_fresh_ts())]
    fresh = expire_old_hazards(reports)
    assert len(fresh) == 1
    print("✓ expire: old report removed, fresh kept")


def test_expire_keeps_fresh():
    """expire_old_hazards must keep all reports younger than MAX_HAZARD_AGE_H."""
    reports = [_make_nearby_report(ts=_fresh_ts()),
               _make_nearby_report(ts=_fresh_ts())]
    fresh = expire_old_hazards(reports)
    assert len(fresh) == 2
    print("✓ expire: all fresh reports kept")


def test_expire_empty_list():
    """expire_old_hazards must handle empty input without error."""
    assert expire_old_hazards([]) == []
    print("✓ expire: empty list → empty list")


# ── Clustering ────────────────────────────────────────────────────────────────

def test_cluster_two_same_type_close():
    """2 black_ice reports within CLUSTER_RADIUS_MI → 1 cluster."""
    reports = [
        {**_make_nearby_report(lat_offset=0.05, htype="black_ice"),
         "ts": _recent_ts()},
        {**_make_nearby_report(lat_offset=0.06, htype="black_ice"),
         "ts": _recent_ts()},
    ]
    clusters = cluster_reports(reports)
    assert len(clusters) == 1
    assert clusters[0]["hazard_type"] == "black_ice"
    assert clusters[0]["driver_count"] == 2
    print("✓ cluster: 2 same-type close reports → 1 cluster")


def test_cluster_single_report_no_cluster():
    """1 report alone must not form a cluster (below CLUSTER_MIN_REPORTS)."""
    reports = [{**_make_nearby_report(lat_offset=0.05), "ts": _recent_ts()}]
    clusters = cluster_reports(reports)
    assert len(clusters) == 0
    print("✓ cluster: single report → no cluster")


def test_cluster_different_types_separate_clusters():
    """black_ice + fog at same location → 2 separate single-type clusters."""
    reports = [
        {**_make_nearby_report(lat_offset=0.05, htype="black_ice"), "ts": _recent_ts()},
        {**_make_nearby_report(lat_offset=0.05, htype="black_ice"), "ts": _recent_ts()},
        {**_make_nearby_report(lat_offset=0.06, htype="fog"),       "ts": _recent_ts()},
        {**_make_nearby_report(lat_offset=0.07, htype="fog"),       "ts": _recent_ts()},
    ]
    clusters = cluster_reports(reports)
    types = {c["hazard_type"] for c in clusters}
    assert "black_ice" in types, "black_ice cluster missing"
    assert "fog"        in types, "fog cluster missing"
    assert len(clusters) == 2
    print("✓ cluster: different types form separate clusters")


def test_cluster_outside_window_excluded():
    """Reports older than CLUSTER_WINDOW_MIN must not form a cluster."""
    reports = [
        {**_make_nearby_report(lat_offset=0.05, htype="black_ice"),
         "ts": _outside_window_ts()},
        {**_make_nearby_report(lat_offset=0.06, htype="black_ice"),
         "ts": _outside_window_ts()},
    ]
    clusters = cluster_reports(reports)
    assert len(clusters) == 0, "Old reports should not cluster"
    print("✓ cluster: outside time window → no cluster")


def test_cluster_centroid_between_two_points():
    """Cluster centroid must be the average lat/lon of the members."""
    lat1, lat2 = HOME_LAT + 0.05, HOME_LAT + 0.07
    reports = [
        {"t": "flood", "lat": lat1, "lon": HOME_LON,
         "ts": _recent_ts(), "sev": "medium", "dir": "unknown",
         "src": "community", "clr": False, "note": ""},
        {"t": "flood", "lat": lat2, "lon": HOME_LON,
         "ts": _recent_ts(), "sev": "medium", "dir": "unknown",
         "src": "community", "clr": False, "note": ""},
    ]
    clusters = cluster_reports(reports)
    assert len(clusters) == 1
    expected_lat = round((lat1 + lat2) / 2, 4)
    assert clusters[0]["center_lat"] == expected_lat, (
        f"Expected centroid {expected_lat}, got {clusters[0]['center_lat']}"
    )
    print(f"✓ cluster: centroid at {clusters[0]['center_lat']}")


def test_cluster_worst_severity_propagates():
    """Cluster severity must be the worst member severity (critical > high > medium > low)."""
    reports = [
        {"t": "ice_storm", "lat": HOME_LAT + 0.05, "lon": HOME_LON,
         "ts": _recent_ts(), "sev": "low",      "dir": "unknown",
         "src": "community", "clr": False, "note": ""},
        {"t": "ice_storm", "lat": HOME_LAT + 0.06, "lon": HOME_LON,
         "ts": _recent_ts(), "sev": "critical", "dir": "unknown",
         "src": "community", "clr": False, "note": ""},
    ]
    clusters = cluster_reports(reports)
    assert len(clusters) == 1
    assert clusters[0]["severity"] == "critical", (
        f"Expected critical, got {clusters[0]['severity']}"
    )
    print("✓ cluster: worst severity (critical) propagates to cluster")


# ── Type and severity mapping ─────────────────────────────────────────────────

def test_hazard_to_alert_type_known_mapping():
    """black_ice maps to 'black_ice' TTS alert type."""
    assert hazard_to_alert_type("black_ice") == "black_ice"
    assert hazard_to_alert_type("fog")       == "fog"
    assert hazard_to_alert_type("flood")     == "flood"
    print("✓ hazard_to_alert_type: known types map correctly")


def test_hazard_to_alert_type_accident_maps_to_generic():
    """Accident and debris both map to 'hazard_reported'."""
    assert hazard_to_alert_type("accident") == "hazard_reported"
    assert hazard_to_alert_type("debris")   == "hazard_reported"
    assert hazard_to_alert_type("other")    == "hazard_reported"
    print("✓ hazard_to_alert_type: accident/debris/other → hazard_reported")


def test_severity_to_tts_mapping():
    """Severity strings map to correct TTS severity levels."""
    assert severity_to_tts("critical") == "CRITICAL"
    assert severity_to_tts("high")     == "WARNING"
    assert severity_to_tts("medium")   == "WARNING"
    assert severity_to_tts("low")      == "INFO"
    assert severity_to_tts("unknown")  == "INFO"    # fallback
    print("✓ severity_to_tts: all levels map correctly")


# ── TTS integration ───────────────────────────────────────────────────────────

def test_speak_nearby_tts_disabled_returns_zero():
    """speak_nearby_hazards must return 0 immediately when TTS is disabled."""
    hazard_list = [
        {"t": "black_ice", "sev": "high", "distance_mi": 5.0}
    ]
    spoken = speak_nearby_hazards(hazard_list, config={"tts_enabled": False})
    assert spoken == 0
    print("✓ speak_nearby_hazards: tts_enabled=False → 0 spoken")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        # Existing parser tests
        test_offline_parser_black_ice,
        test_offline_parser_fog,
        test_offline_parser_fallback,
        # Data budget
        test_report_under_200_bytes,
        test_report_long_note_trimmed_by_submit,
        # Report construction
        test_make_report_all_fields_present,
        test_make_report_timestamp_is_recent,
        test_make_report_coordinates_rounded,
        # Submit
        test_submit_hazard_returns_true,
        test_submit_hazard_stores_report,
        test_submit_hazard_explicit_type_overrides_parsed,
        test_submit_hazard_parses_description,
        # Nearby filtering
        test_nearby_within_radius_included,
        test_nearby_outside_radius_excluded,
        test_nearby_expired_excluded,
        test_nearby_fresh_included,
        test_nearby_cleared_excluded,
        test_nearby_sorted_closest_first,
        # Expiry
        test_expire_removes_old,
        test_expire_keeps_fresh,
        test_expire_empty_list,
        # Clustering
        test_cluster_two_same_type_close,
        test_cluster_single_report_no_cluster,
        test_cluster_different_types_separate_clusters,
        test_cluster_outside_window_excluded,
        test_cluster_centroid_between_two_points,
        test_cluster_worst_severity_propagates,
        # Mapping
        test_hazard_to_alert_type_known_mapping,
        test_hazard_to_alert_type_accident_maps_to_generic,
        test_severity_to_tts_mapping,
        # TTS
        test_speak_nearby_tts_disabled_returns_zero,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1

    print()
    print(f"{'=' * 45}")
    print(f"  hazards: {passed} passed, {failed} failed")
    if failed:
        print(f"  SOME TESTS FAILED")
        sys.exit(1)
    else:
        print(f"  All hazard tests passed.")
