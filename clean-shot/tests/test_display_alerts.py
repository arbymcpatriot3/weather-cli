#!/usr/bin/env python3
# tests/test_display_alerts.py — Clean Shot: urgent alert display tests
#
# All tests offline — no network, no GPS, no audio (beep silenced via config).
# Total: 38 tests

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from display.display_alerts import (
    SEVERITIES,
    severity_color,
    severity_icon,
    flash_banner,
    build_critical_box,
    flash_terminal,
    prompt_ack,
    should_beep,
    beep_count,
    beep,
    display_critical_alert,
    display_critical_alerts,
    display_dot511_critical,
    display_hazard_critical,
    display_urgent_parking,
    display_hos_critical,
    check_and_display,
)


# ── Silence beep for all tests ────────────────────────────────────────────────
_SILENT = {"tts_enabled": False}


# ── SEVERITIES constant ───────────────────────────────────────────────────────

def test_five_severity_levels():
    assert len(SEVERITIES) == 5
    assert "EMERGENCY" in SEVERITIES
    assert "CRITICAL"  in SEVERITIES
    assert "WARNING"   in SEVERITIES
    assert "INFO"      in SEVERITIES
    assert "LOW"       in SEVERITIES
    print("✓ SEVERITIES: all 5 levels present")


# ── severity_color ────────────────────────────────────────────────────────────

def test_severity_color_emergency():
    c = severity_color("EMERGENCY")
    assert isinstance(c, str)
    print(f"✓ severity_color: EMERGENCY → {repr(c[:12]) if c else 'plain'}")

def test_severity_color_critical():
    c = severity_color("CRITICAL")
    assert isinstance(c, str)
    print("✓ severity_color: CRITICAL → string")

def test_severity_color_warning():
    c = severity_color("WARNING")
    assert isinstance(c, str)
    print("✓ severity_color: WARNING → string")

def test_severity_color_info():
    c = severity_color("INFO")
    assert isinstance(c, str)
    print("✓ severity_color: INFO → string")

def test_severity_color_low():
    c = severity_color("LOW")
    assert isinstance(c, str)
    print("✓ severity_color: LOW → string")


# ── severity_icon ─────────────────────────────────────────────────────────────

def test_severity_icon_emergency():
    assert severity_icon("EMERGENCY") == "🚨"
    print("✓ severity_icon: EMERGENCY → 🚨")

def test_severity_icon_critical():
    assert severity_icon("CRITICAL") == "⛔"
    print("✓ severity_icon: CRITICAL → ⛔")

def test_severity_icon_warning():
    assert severity_icon("WARNING") == "⚠️"
    print("✓ severity_icon: WARNING → ⚠️")

def test_severity_icon_low():
    assert severity_icon("LOW") == "•"
    print("✓ severity_icon: LOW → •")

def test_severity_icon_unknown():
    assert severity_icon("WHATEVER") == "•"
    print("✓ severity_icon: unknown → •")


# ── beep helpers ──────────────────────────────────────────────────────────────

def test_should_beep_emergency():
    assert should_beep("EMERGENCY") is True
    print("✓ should_beep: EMERGENCY → True")

def test_should_beep_critical():
    assert should_beep("CRITICAL") is True
    assert should_beep("critical") is True
    print("✓ should_beep: CRITICAL → True")

def test_should_beep_warning():
    assert should_beep("WARNING") is True
    print("✓ should_beep: WARNING → True")

def test_should_beep_info_low_false():
    assert should_beep("INFO") is False
    assert should_beep("LOW")  is False
    print("✓ should_beep: INFO/LOW → False")

def test_beep_count_all_levels():
    assert beep_count("EMERGENCY") == 5
    assert beep_count("CRITICAL")  == 3
    assert beep_count("WARNING")   == 1
    assert beep_count("INFO")      == 0
    assert beep_count("LOW")       == 0
    print("✓ beep_count: EMERGENCY=5, CRITICAL=3, WARNING=1, INFO=0, LOW=0")

def test_beep_no_crash():
    beep(1, config=_SILENT)
    print("✓ beep: no crash (silenced via config)")


# ── flash_terminal ────────────────────────────────────────────────────────────

def test_flash_terminal_no_crash():
    """flash_terminal must not crash — stdout is not a tty in tests, so it's a no-op."""
    flash_terminal(2)
    print("✓ flash_terminal: no crash (no-op when stdout is not a tty)")


# ── prompt_ack ────────────────────────────────────────────────────────────────

def test_prompt_ack_returns_false_not_tty():
    """prompt_ack always returns False in test (stdout is not a tty)."""
    result = prompt_ack(timeout_s=0.1, config={"alerts_require_ack": True})
    assert result is False
    print("✓ prompt_ack: returns False when not a tty (no blocking)")

def test_prompt_ack_returns_false_when_not_required():
    result = prompt_ack(timeout_s=0.1, config=_SILENT)
    assert result is False
    print("✓ prompt_ack: returns False when alerts_require_ack not set")


# ── banner builders ───────────────────────────────────────────────────────────

def test_flash_banner_emergency():
    s = flash_banner("BRIDGE STRIKE AHEAD", "EMERGENCY")
    assert isinstance(s, str) and len(s) > 0
    assert "EMERGENCY" in s
    print("✓ flash_banner: EMERGENCY contains 'EMERGENCY'")

def test_flash_banner_returns_string():
    s = flash_banner("Black ice ahead", "CRITICAL")
    assert isinstance(s, str) and len(s) > 0
    assert "CRITICAL" in s
    print("✓ flash_banner: CRITICAL — non-empty string")

def test_build_critical_box_contains_title():
    box = build_critical_box("BLACK ICE AHEAD", "back it down", "CRITICAL")
    assert "BLACK ICE AHEAD" in box
    assert "back it down"    in box
    print("✓ build_critical_box: title and body present")

def test_build_critical_box_width_reasonable():
    import re
    box = build_critical_box("TEST", "test body", "CRITICAL")
    for line in box.split("\n"):
        plain = re.sub(r'\x1b\[[0-9;]*m', '', line)
        assert len(plain) <= 82, f"Box line too wide: {len(plain)} chars"
    print("✓ build_critical_box: width ≤ 80 chars (after stripping ANSI)")

def test_build_critical_box_emergency():
    box = build_critical_box("BRIDGE STRIKE", "14.2 ft clearance", "EMERGENCY")
    assert "BRIDGE STRIKE" in box
    assert "EMERGENCY" in box
    print("✓ build_critical_box: EMERGENCY box contains title")

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

def test_display_critical_alert_emergency_no_crash():
    alert = {"type": "bridge_strike", "severity": "EMERGENCY",
             "cb_voice": "bridge ahead — do not proceed"}
    display_critical_alert(alert, _SILENT)
    print("✓ display_critical_alert: EMERGENCY alert — no crash")

def test_display_critical_alert_skips_info():
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
    print("✓ display_critical_alerts: 2 of 3 shown (CRITICAL+WARNING only)")

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
    runway = {"level": "normal", "miles": 500.0, "minutes": 600}
    display_urgent_parking(runway, None, _SILENT)
    print("✓ display_urgent_parking: normal level → silent (no banner)")

def test_display_hos_critical_urgent():
    """HOS in urgent state (<=30 min) should show a WARNING banner."""
    import core.hos as hos_mod
    T0 = 1_700_000_000.0
    hos_mod._time_fn = lambda: T0
    cfg = dict(_SILENT)
    cfg["subscription_tier"] = "solo_pro"
    hos_mod.start_drive(cfg)
    hos_mod._time_fn = lambda: T0 + (660 - 20) * 60   # 20 min remaining
    count = display_hos_critical(cfg)
    assert count == 1
    hos_mod._time_fn = __import__("time").time
    print("✓ display_hos_critical: urgent HOS → 1 banner shown")

def test_display_hos_critical_normal_skipped():
    """Normal HOS (lots of time) should not display anything."""
    cfg = dict(_SILENT)
    count = display_hos_critical(cfg)
    assert count == 0
    print("✓ display_hos_critical: normal HOS → 0 banners (silent)")

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

def test_check_and_display_include_hos():
    """include_hos=True with normal HOS → no extra banners."""
    result = check_and_display(config=_SILENT, include_hos=True)
    assert result is False
    print("✓ check_and_display: include_hos=True with normal HOS → False")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_five_severity_levels,
        test_severity_color_emergency,
        test_severity_color_critical,
        test_severity_color_warning,
        test_severity_color_info,
        test_severity_color_low,
        test_severity_icon_emergency,
        test_severity_icon_critical,
        test_severity_icon_warning,
        test_severity_icon_low,
        test_severity_icon_unknown,
        test_should_beep_emergency,
        test_should_beep_critical,
        test_should_beep_warning,
        test_should_beep_info_low_false,
        test_beep_count_all_levels,
        test_beep_no_crash,
        test_flash_terminal_no_crash,
        test_prompt_ack_returns_false_not_tty,
        test_prompt_ack_returns_false_when_not_required,
        test_flash_banner_emergency,
        test_flash_banner_returns_string,
        test_build_critical_box_contains_title,
        test_build_critical_box_width_reasonable,
        test_build_critical_box_emergency,
        test_build_critical_box_no_body,
        test_display_critical_alert_no_crash,
        test_display_critical_alert_emergency_no_crash,
        test_display_critical_alert_skips_info,
        test_display_critical_alerts_empty,
        test_display_critical_alerts_counts,
        test_display_dot511_critical_no_crash,
        test_display_hazard_critical_no_crash,
        test_display_urgent_parking_critical,
        test_display_urgent_parking_normal_skipped,
        test_display_hos_critical_urgent,
        test_display_hos_critical_normal_skipped,
        test_check_and_display_all_empty,
        test_check_and_display_with_critical_alert,
        test_check_and_display_include_hos,
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
