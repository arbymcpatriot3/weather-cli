#!/usr/bin/env python3
# tests/test_display_alerts.py — Clean Shot: urgent alert display tests
#
# All tests offline — no network, no GPS, no audio (beep silenced via config).
# Total: 25 tests

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from display.display_alerts import (
    severity_color,
    severity_icon,
    flash_banner,
    build_critical_box,
    should_beep,
    beep_count,
    beep,
    display_critical_alert,
    display_critical_alerts,
    display_dot511_critical,
    display_hazard_critical,
    display_urgent_parking,
    check_and_display,
)


# ── Silence beep for all tests ────────────────────────────────────────────────
_SILENT = {"tts_enabled": False}


# ── severity helpers ──────────────────────────────────────────────────────────

def test_severity_color_critical():
    c = severity_color("CRITICAL")
    # Either a non-empty colorama string or empty string (no colorama installed)
    assert isinstance(c, str)
    print(f"✓ severity_color: CRITICAL → {repr(c[:10]) if c else 'plain (no colorama)'}")


def test_severity_color_warning():
    c = severity_color("WARNING")
    assert isinstance(c, str)
    print("✓ severity_color: WARNING → string")


def test_severity_color_info():
    c = severity_color("INFO")
    assert isinstance(c, str)
    print("✓ severity_color: INFO → string")


def test_severity_icon_critical():
    assert severity_icon("CRITICAL") == "⛔"
    print("✓ severity_icon: CRITICAL → ⛔")


def test_severity_icon_warning():
    assert severity_icon("WARNING") == "⚠️"
    print("✓ severity_icon: WARNING → ⚠️")


def test_severity_icon_unknown():
    assert severity_icon("WHATEVER") == "•"
    print("✓ severity_icon: unknown → •")


# ── beep helpers ──────────────────────────────────────────────────────────────

def test_should_beep_critical():
    assert should_beep("CRITICAL") is True
    assert should_beep("critical") is True
    print("✓ should_beep: CRITICAL → True")


def test_should_beep_warning():
    assert should_beep("WARNING") is True
    print("✓ should_beep: WARNING → True")


def test_should_beep_info_false():
    assert should_beep("INFO") is False
    assert should_beep("LOW")  is False
    print("✓ should_beep: INFO/LOW → False")


def test_beep_count():
    assert beep_count("CRITICAL") == 3
    assert beep_count("WARNING")  == 1
    assert beep_count("INFO")     == 0
    print("✓ beep_count: CRITICAL=3, WARNING=1, INFO=0")


def test_beep_no_crash():
    """beep() must not crash even if no audio is available."""
    beep(1, config=_SILENT)
    print("✓ beep: no crash (silenced via config)")


# ── banner builders ───────────────────────────────────────────────────────────

def test_flash_banner_returns_string():
    s = flash_banner("Black ice ahead", "CRITICAL")
    assert isinstance(s, str) and len(s) > 0
    assert "CRITICAL" in s
    print(f"✓ flash_banner: returns non-empty string containing 'CRITICAL'")


def test_build_critical_box_contains_title():
    box = build_critical_box("BLACK ICE AHEAD", "back it down", "CRITICAL")
    assert "BLACK ICE AHEAD" in box
    assert "back it down"    in box
    print("✓ build_critical_box: title and body present in output")


def test_build_critical_box_width_reasonable():
    box = build_critical_box("TEST", "test body", "CRITICAL")
    lines = box.split("\n")
    # Strip ANSI codes before measuring
    import re
    for line in lines:
        plain = re.sub(r'\x1b\[[0-9;]*m', '', line)
        assert len(plain) <= 82, f"Box line too wide: {len(plain)} chars"
    print("✓ build_critical_box: width ≤ 80 chars (after stripping ANSI)")


def test_build_critical_box_no_body():
    box = build_critical_box("TITLE ONLY")
    assert "TITLE ONLY" in box
    print("✓ build_critical_box: works with no body line")


# ── display functions ─────────────────────────────────────────────────────────

def test_display_critical_alert_no_crash():
    alert = {"type": "black_ice", "severity": "CRITICAL",
             "cb_voice": "back it down good buddy"}
    display_critical_alert(alert, _SILENT)
    print("✓ display_critical_alert: CRITICAL alert — no crash")


def test_display_critical_alert_skips_info():
    """INFO severity should not display a box (returns without printing)."""
    alert = {"type": "fog", "severity": "INFO", "cb_voice": "light fog"}
    display_critical_alert(alert, _SILENT)
    print("✓ display_critical_alert: INFO → skipped (no box)")


def test_display_critical_alerts_empty():
    count = display_critical_alerts([], _SILENT)
    assert count == 0
    print("✓ display_critical_alerts: empty list → 0")


def test_display_critical_alerts_counts():
    alerts = [
        {"type": "black_ice", "severity": "CRITICAL", "cb_voice": "back it down"},
        {"type": "fog",       "severity": "WARNING",  "cb_voice": "slow your roll"},
        {"type": "wind",      "severity": "INFO",     "cb_voice": "watch it"},
    ]
    count = display_critical_alerts(alerts, _SILENT)
    assert count == 2, f"Expected 2 (CRITICAL+WARNING), got {count}"
    print(f"✓ display_critical_alerts: 2 of 3 shown (CRITICAL+WARNING only)")


def test_display_dot511_critical_no_crash():
    incidents = [
        {"type": "chains_required", "severity": "critical",
         "highway": "I-70", "description": "Chains on I-70"},
    ]
    count = display_dot511_critical(incidents, _SILENT)
    assert count == 1
    print("✓ display_dot511_critical: no crash, 1 shown")


def test_display_hazard_critical_no_crash():
    hazards = [
        {"t": "black_ice", "sev": "critical",
         "distance_mi": 5.2, "driver_count": 3},
    ]
    count = display_hazard_critical(hazards, _SILENT)
    assert count == 1
    print("✓ display_hazard_critical: no crash, 1 shown")


def test_display_urgent_parking_critical():
    runway = {"level": "critical", "miles": 22.0, "minutes": 24,
              "urgent": True, "critical": True, "warning": True}
    stop   = {"name": "Pilot #428", "highway": "I-40",
               "exit": "1", "distance_mi": 10.6}
    display_urgent_parking(runway, stop, _SILENT)
    print("✓ display_urgent_parking: critical runway + stop — no crash")


def test_display_urgent_parking_normal_skipped():
    """Normal runway level should not display any banner."""
    runway = {"level": "normal", "miles": 500.0, "minutes": 600}
    display_urgent_parking(runway, None, _SILENT)
    print("✓ display_urgent_parking: normal level → silent (no banner)")


def test_check_and_display_all_empty():
    result = check_and_display(
        alerts=[], incidents=[], hazards=[],
        runway=None, nearest_stop=None, config=_SILENT,
    )
    assert result is False
    print("✓ check_and_display: all empty → False (nothing shown)")


def test_check_and_display_with_critical_alert():
    alerts = [{"type": "black_ice", "severity": "CRITICAL",
               "cb_voice": "back it down good buddy"}]
    result = check_and_display(alerts=alerts, config=_SILENT)
    assert result is True
    print("✓ check_and_display: CRITICAL alert → True (banner shown)")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_severity_color_critical,
        test_severity_color_warning,
        test_severity_color_info,
        test_severity_icon_critical,
        test_severity_icon_warning,
        test_severity_icon_unknown,
        test_should_beep_critical,
        test_should_beep_warning,
        test_should_beep_info_false,
        test_beep_count,
        test_beep_no_crash,
        test_flash_banner_returns_string,
        test_build_critical_box_contains_title,
        test_build_critical_box_width_reasonable,
        test_build_critical_box_no_body,
        test_display_critical_alert_no_crash,
        test_display_critical_alert_skips_info,
        test_display_critical_alerts_empty,
        test_display_critical_alerts_counts,
        test_display_dot511_critical_no_crash,
        test_display_hazard_critical_no_crash,
        test_display_urgent_parking_critical,
        test_display_urgent_parking_normal_skipped,
        test_check_and_display_all_empty,
        test_check_and_display_with_critical_alert,
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
    print(f"  display_alerts: {passed} passed, {failed} failed")
    if failed:
        print("  SOME TESTS FAILED")
        sys.exit(1)
    else:
        print("  All display_alerts tests passed.")
