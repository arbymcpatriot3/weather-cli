#!/usr/bin/env python3
# tests/test_hos.py — Clean Shot: HOS Guardian tests
#
# All tests offline — no GPS, no network, no audio.
# Time is fully mocked via hos._time_fn so elapsed calculations are exact.
# Total: 42 tests

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core.hos as hos
from core.hos import (
    HOS_DRIVE_LIMIT_MIN,
    HOS_DUTY_LIMIT_MIN,
    HOS_BREAK_TRIGGER_MIN,
    HOS_BREAK_REQUIRED_MIN,
    HOS_RESET_MIN,
    HOS_WEEKLY_60_MIN,
    HOS_WEEKLY_70_MIN,
    get_hos_status,
    start_drive,
    stop_drive,
    start_duty,
    end_duty,
    take_break,
    reset_hos,
    needs_break,
    minutes_until_break_required,
    add_duty_to_weekly,
    reset_weekly,
    get_weekly_remaining,
    check_hos_thresholds,
    reset_announcements,
    update_elapsed,
    format_hos_str,
    display_hos_status,
    _urgency_level,
)

# ── Time mock helpers ─────────────────────────────────────────────────────────

_T0 = 1_700_000_000.0   # arbitrary fixed epoch (seconds)

def _set_time(t: float):
    hos._time_fn = lambda: t

def _advance(seconds: float):
    current = hos._time_fn()
    hos._time_fn = lambda: current + seconds

def _reset_time():
    hos._time_fn = __import__("time").time


# ── Fresh config helper ───────────────────────────────────────────────────────

def _cfg(**overrides) -> dict:
    """Return a minimal clean config with solo_pro tier."""
    c = {"subscription_tier": "solo_pro", "tts_enabled": False}
    c.update(overrides)
    return c


# ── Constants ─────────────────────────────────────────────────────────────────

def test_drive_limit_is_11h():
    assert HOS_DRIVE_LIMIT_MIN == 660
    print("✓ HOS_DRIVE_LIMIT_MIN == 660 (11 hours)")

def test_duty_limit_is_14h():
    assert HOS_DUTY_LIMIT_MIN == 840
    print("✓ HOS_DUTY_LIMIT_MIN == 840 (14 hours)")

def test_break_trigger_is_8h():
    assert HOS_BREAK_TRIGGER_MIN == 480
    print("✓ HOS_BREAK_TRIGGER_MIN == 480 (8 hours)")

def test_break_required_is_30min():
    assert HOS_BREAK_REQUIRED_MIN == 30
    print("✓ HOS_BREAK_REQUIRED_MIN == 30")

def test_reset_is_10h():
    assert HOS_RESET_MIN == 600
    print("✓ HOS_RESET_MIN == 600 (10 hours)")

def test_weekly_limits():
    assert HOS_WEEKLY_60_MIN == 3600
    assert HOS_WEEKLY_70_MIN == 4200
    print("✓ Weekly limits: 60h=3600 min, 70h=4200 min")


# ── Fresh config (no session) ─────────────────────────────────────────────────

def test_fresh_status_full_drive():
    cfg = _cfg()
    s = get_hos_status(cfg)
    assert s["drive_remaining_min"] == HOS_DRIVE_LIMIT_MIN
    assert s["level"] == "normal"
    assert s["needs_break"] is False
    assert s["violation_risk"] is False
    assert s["has_session"] is False
    print("✓ Fresh status: full 11h drive remaining, normal level")

def test_fresh_status_writes_parking_feed():
    cfg = _cfg()
    get_hos_status(cfg)
    assert cfg["hos_drive_remaining_min"] == float(HOS_DRIVE_LIMIT_MIN)
    print("✓ get_hos_status writes hos_drive_remaining_min to config")

def test_fresh_no_duty_session():
    cfg = _cfg()
    s = get_hos_status(cfg)
    assert s["is_driving"] is False
    assert s["is_on_duty"] is False
    assert s["has_session"] is False
    print("✓ Fresh config: not driving, not on duty, no session")


# ── start/stop drive ─────────────────────────────────────────────────────────

def test_start_drive_sets_flags():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    assert cfg["hos_is_driving"] is True
    assert cfg["hos_is_on_duty"] is True
    assert cfg["hos_session_start_ts"] == _T0
    assert cfg["hos_drive_start_ts"] == _T0
    print("✓ start_drive: sets is_driving, is_on_duty, timestamps")

def test_stop_drive_accumulates():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance(120 * 60)   # drive 2 hours
    stop_drive(cfg)
    assert cfg["hos_is_driving"] is False
    assert cfg["hos_drive_start_ts"] is None
    assert abs(cfg["hos_drive_elapsed_min"] - 120.0) < 0.01
    print("✓ stop_drive: 2h segment accumulated correctly")

def test_multiple_drive_segments_accumulate():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance(3 * 60 * 60)  # 3h
    stop_drive(cfg)
    _advance(1 * 60 * 60)  # 1h parked (on duty)
    start_drive(cfg)
    _advance(2 * 60 * 60)  # 2h
    stop_drive(cfg)
    # Total: 5 hours driving
    assert abs(cfg["hos_drive_elapsed_min"] - 300.0) < 0.01
    print("✓ Multiple drive segments: 3h + 2h = 5h accumulated")

def test_drive_remaining_decreases_as_driving():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance(4 * 60 * 60)  # 4h of driving
    s = get_hos_status(cfg)
    assert s["drive_remaining_min"] == 660 - 240
    print(f"✓ drive_remaining_min: {s['drive_remaining_min']} after 4h driving")

def test_drive_remaining_never_negative():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance(12 * 60 * 60)  # 12h — exceeds 11h limit
    s = get_hos_status(cfg)
    assert s["drive_remaining_min"] == 0
    print("✓ drive_remaining_min: 0 when 11h exceeded (never negative)")

def test_stop_drive_when_not_driving_is_safe():
    cfg = _cfg()
    stop_drive(cfg)   # should not crash
    print("✓ stop_drive when not driving: no crash")

def test_start_drive_twice_no_double_count():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance(60)
    start_drive(cfg)   # second call — should be no-op
    _advance(60)
    stop_drive(cfg)
    # Should be 2 minutes total, not 3
    assert abs(cfg["hos_drive_elapsed_min"] - 2.0) < 0.01
    print("✓ start_drive twice: no double-counting")


# ── Duty window (14h wall clock) ─────────────────────────────────────────────

def test_duty_window_ticks_even_when_parked():
    _set_time(_T0)
    cfg = _cfg()
    start_duty(cfg)
    _advance(2 * 60 * 60)   # 2h on duty, not driving
    s = get_hos_status(cfg)
    assert s["is_on_duty"] is True
    assert s["duty_remaining_min"] == 840 - 120
    assert s["drive_remaining_min"] == 660   # drive time unchanged
    print("✓ duty window ticks while parked; drive time unchanged")

def test_duty_remaining_never_negative():
    _set_time(_T0)
    cfg = _cfg()
    start_duty(cfg)
    _advance(15 * 60 * 60)   # 15h — exceeds 14h wall
    s = get_hos_status(cfg)
    assert s["duty_remaining_min"] == 0
    print("✓ duty_remaining_min: 0 when 14h wall exceeded")

def test_end_duty_clears_on_duty_flag():
    _set_time(_T0)
    cfg = _cfg()
    start_duty(cfg)
    _advance(60)
    end_duty(cfg)
    assert cfg["hos_is_on_duty"] is False
    print("✓ end_duty: clears is_on_duty flag")

def test_effective_is_minimum_of_drive_and_duty():
    _set_time(_T0)
    cfg = _cfg()
    # Drive 10.5h = 630 min → drive_remaining = 30 min
    # But duty has only been running 11h = 660 min → duty_remaining = 180 min
    # Effective = min(30, 180) = 30
    start_drive(cfg)
    _advance(10.5 * 60 * 60)
    s = get_hos_status(cfg)
    assert s["effective_remaining_min"] == s["drive_remaining_min"]
    assert s["effective_remaining_min"] <= s["duty_remaining_min"]
    print(f"✓ effective = min(drive={s['drive_remaining_min']}, duty={s['duty_remaining_min']})")


# ── Break rule ────────────────────────────────────────────────────────────────

def test_break_not_needed_under_8h():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance(7 * 60 * 60)   # 7h driving
    assert needs_break(cfg) is False
    print("✓ needs_break: False after 7h driving")

def test_break_needed_at_8h():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance(8 * 60 * 60)   # exactly 8h
    assert needs_break(cfg) is True
    print("✓ needs_break: True at exactly 8h driving")

def test_take_break_resets_counter():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance(9 * 60 * 60)   # 9h
    stop_drive(cfg)
    take_break(cfg)
    assert cfg["hos_break_drive_min"] == 0.0
    assert needs_break(cfg) is False
    print("✓ take_break: resets break_drive_min to 0")

def test_take_break_does_not_reset_11h_window():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance(9 * 60 * 60)   # 9h driving
    stop_drive(cfg)
    take_break(cfg)
    s = get_hos_status(cfg)
    # 9h used, 2h left
    assert s["drive_remaining_min"] == 660 - 540
    print(f"✓ take_break: 11h window intact ({s['drive_remaining_min']} min remaining)")

def test_minutes_until_break_required():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance(6 * 60 * 60)   # 6h driving
    remaining = minutes_until_break_required(cfg)
    assert abs(remaining - 120.0) < 0.1   # 2h = 120 min left
    print(f"✓ minutes_until_break_required: {remaining:.1f} min after 6h driving")

def test_minutes_until_break_zero_when_overdue():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance(9 * 60 * 60)
    assert minutes_until_break_required(cfg) == 0.0
    print("✓ minutes_until_break_required: 0 when break already overdue")


# ── reset_hos ─────────────────────────────────────────────────────────────────

def test_reset_hos_clears_all():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance(5 * 60 * 60)
    stop_drive(cfg)
    reset_hos(cfg)
    assert cfg["hos_drive_elapsed_min"] == 0.0
    assert cfg["hos_break_drive_min"]   == 0.0
    assert cfg["hos_session_start_ts"]  is None
    assert cfg["hos_is_driving"]        is False
    assert cfg["hos_is_on_duty"]        is False
    s = get_hos_status(cfg)
    assert s["drive_remaining_min"] == HOS_DRIVE_LIMIT_MIN
    print("✓ reset_hos: all counters cleared, full limits restored")

def test_reset_hos_while_driving():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance(60 * 60)
    reset_hos(cfg)
    assert cfg["hos_is_driving"] is False
    print("✓ reset_hos while driving: safe (stops drive segment first)")


# ── Urgency levels ────────────────────────────────────────────────────────────

def test_urgency_level_normal():
    assert _urgency_level(661) == "normal"
    assert _urgency_level(61)  == "normal"
    print("✓ urgency_level: normal above 60 min")

def test_urgency_level_warning():
    assert _urgency_level(60) == "warning"
    assert _urgency_level(31) == "warning"
    print("✓ urgency_level: warning 31-60 min")

def test_urgency_level_urgent():
    assert _urgency_level(30) == "urgent"
    assert _urgency_level(16) == "urgent"
    print("✓ urgency_level: urgent 16-30 min")

def test_urgency_level_critical():
    assert _urgency_level(15) == "critical"
    assert _urgency_level(0)  == "critical"
    print("✓ urgency_level: critical at 15 min and below")

def test_status_level_critical_when_nearly_expired():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance((660 - 10) * 60)   # 10 min left
    s = get_hos_status(cfg)
    assert s["level"] == "critical"
    assert s["violation_imminent"] is True
    assert s["violation_risk"] is True
    print("✓ status level = critical, violation_imminent = True at 10 min")

def test_status_level_urgent_at_20min():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance((660 - 20) * 60)   # 20 min left
    s = get_hos_status(cfg)
    assert s["level"] == "urgent"
    assert s["violation_risk"] is True
    assert s["violation_imminent"] is False
    print("✓ status level = urgent at 20 min remaining")

def test_violation_risk_false_with_plenty_of_time():
    cfg = _cfg()
    s = get_hos_status(cfg)
    assert s["violation_risk"] is False
    print("✓ violation_risk: False on fresh config")


# ── Weekly limit ──────────────────────────────────────────────────────────────

def test_weekly_limit_70_8_default():
    cfg = _cfg()
    remaining = get_weekly_remaining(cfg)
    assert remaining == float(HOS_WEEKLY_70_MIN)
    print(f"✓ Weekly 70/8 default: {remaining:.0f} min remaining")

def test_weekly_limit_60_7_cycle():
    cfg = _cfg(hos_cycle="60_7")
    remaining = get_weekly_remaining(cfg)
    assert remaining == float(HOS_WEEKLY_60_MIN)
    print(f"✓ Weekly 60/7 cycle: {remaining:.0f} min remaining")

def test_add_duty_to_weekly():
    cfg = _cfg()
    add_duty_to_weekly(cfg, 600.0)   # 10 hours
    assert cfg["hos_7day_duty_min"] == 600.0
    print("✓ add_duty_to_weekly: 600 min added")

def test_weekly_remaining_decreases():
    cfg = _cfg()
    add_duty_to_weekly(cfg, 3000.0)   # 50 hours used
    remaining = get_weekly_remaining(cfg)
    assert remaining == HOS_WEEKLY_70_MIN - 3000.0
    print(f"✓ Weekly remaining after 50h used: {remaining:.0f} min")

def test_reset_weekly():
    cfg = _cfg()
    add_duty_to_weekly(cfg, 2000.0)
    reset_weekly(cfg)
    assert cfg["hos_7day_duty_min"] == 0.0
    print("✓ reset_weekly: counter cleared")

def test_weekly_remaining_never_negative():
    cfg = _cfg()
    add_duty_to_weekly(cfg, 9999.0)   # way over limit
    remaining = get_weekly_remaining(cfg)
    assert remaining == 0.0
    print("✓ Weekly remaining: 0 when exceeded (never negative)")


# ── check_hos_thresholds ──────────────────────────────────────────────────────

def test_thresholds_none_crossed_on_fresh():
    cfg = _cfg()
    crossed = check_hos_thresholds(cfg)
    assert crossed == []
    print("✓ check_hos_thresholds: none crossed on fresh config")

def test_thresholds_crossed_at_15min():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance((660 - 10) * 60)   # 10 min left — crosses 15 and 30 and 60 and 120
    crossed = check_hos_thresholds(cfg)
    thresh_mins = [t[0] for t in crossed]
    assert 15  in thresh_mins
    assert 30  in thresh_mins
    assert 60  in thresh_mins
    assert 120 in thresh_mins
    print(f"✓ check_hos_thresholds: {len(crossed)} thresholds crossed at 10 min remaining")

def test_thresholds_only_crossed_above_remaining():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance((660 - 45) * 60)   # 45 min left — crosses 60 and 120 (effective <= thresh)
    crossed = check_hos_thresholds(cfg)
    thresh_mins = [t[0] for t in crossed]
    assert 60  in thresh_mins    # 45 <= 60 → crossed
    assert 120 in thresh_mins    # 45 <= 120 → crossed
    assert 30 not in thresh_mins  # 45 > 30 → not yet crossed
    assert 15 not in thresh_mins  # 45 > 15 → not yet crossed
    print(f"✓ check_hos_thresholds: 60 and 120 crossed at 45 min remaining")


# ── update_elapsed ────────────────────────────────────────────────────────────

def test_update_elapsed_refreshes_parking_feed():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance(2 * 60 * 60)   # 2h
    update_elapsed(cfg)
    # parking feed should reflect 2h less = 660-120 = 540
    assert cfg["hos_drive_remaining_min"] == 660 - 120
    print(f"✓ update_elapsed: parking feed = {cfg['hos_drive_remaining_min']}")


# ── format_hos_str ────────────────────────────────────────────────────────────

def test_format_hos_str_contains_drive():
    cfg = _cfg()
    s = get_hos_status(cfg)
    text = format_hos_str(s)
    assert "HOS" in text
    assert "Drive" in text
    assert "ADVISORY" in text
    print(f"✓ format_hos_str: {text[:60]}...")

def test_format_hos_str_shows_break_required():
    _set_time(_T0)
    cfg = _cfg()
    start_drive(cfg)
    _advance(9 * 60 * 60)   # break required
    s = get_hos_status(cfg)
    text = format_hos_str(s)
    assert "BREAK" in text
    print("✓ format_hos_str: BREAK REQUIRED shown when needed")


# ── display_hos_status ────────────────────────────────────────────────────────

def test_display_hos_status_no_crash_solo_pro():
    cfg = _cfg()
    display_hos_status(cfg)
    print("✓ display_hos_status: no crash (solo_pro)")

def test_display_hos_status_free_tier_upgrade_prompt():
    import io, contextlib, time
    # Simulate expired trial (trial_start > 30 days ago) so gating applies
    expired_start = time.time() - (31 * 86400)
    cfg = {"subscription_tier": "free", "tts_enabled": False, "trial_start": expired_start}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        display_hos_status(cfg)
    assert "Solo Pro" in buf.getvalue() or "upgrade" in buf.getvalue().lower()
    print("✓ display_hos_status: upgrade prompt for expired-trial free tier")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_drive_limit_is_11h,
        test_duty_limit_is_14h,
        test_break_trigger_is_8h,
        test_break_required_is_30min,
        test_reset_is_10h,
        test_weekly_limits,
        test_fresh_status_full_drive,
        test_fresh_status_writes_parking_feed,
        test_fresh_no_duty_session,
        test_start_drive_sets_flags,
        test_stop_drive_accumulates,
        test_multiple_drive_segments_accumulate,
        test_drive_remaining_decreases_as_driving,
        test_drive_remaining_never_negative,
        test_stop_drive_when_not_driving_is_safe,
        test_start_drive_twice_no_double_count,
        test_duty_window_ticks_even_when_parked,
        test_duty_remaining_never_negative,
        test_end_duty_clears_on_duty_flag,
        test_effective_is_minimum_of_drive_and_duty,
        test_break_not_needed_under_8h,
        test_break_needed_at_8h,
        test_take_break_resets_counter,
        test_take_break_does_not_reset_11h_window,
        test_minutes_until_break_required,
        test_minutes_until_break_zero_when_overdue,
        test_reset_hos_clears_all,
        test_reset_hos_while_driving,
        test_urgency_level_normal,
        test_urgency_level_warning,
        test_urgency_level_urgent,
        test_urgency_level_critical,
        test_status_level_critical_when_nearly_expired,
        test_status_level_urgent_at_20min,
        test_violation_risk_false_with_plenty_of_time,
        test_weekly_limit_70_8_default,
        test_weekly_limit_60_7_cycle,
        test_add_duty_to_weekly,
        test_weekly_remaining_decreases,
        test_reset_weekly,
        test_weekly_remaining_never_negative,
        test_thresholds_none_crossed_on_fresh,
        test_thresholds_crossed_at_15min,
        test_thresholds_only_crossed_above_remaining,
        test_update_elapsed_refreshes_parking_feed,
        test_format_hos_str_contains_drive,
        test_format_hos_str_shows_break_required,
        test_display_hos_status_no_crash_solo_pro,
        test_display_hos_status_free_tier_upgrade_prompt,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            _set_time(_T0)          # reset clock before each test
            reset_announcements()   # reset per-trip announcement state
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    _reset_time()
    print()
    print(f"{'=' * 50}")
    print(f"  hos: {passed} passed, {failed} failed")
    if failed:
        print("  SOME TESTS FAILED")
        sys.exit(1)
    else:
        print("  All HOS tests passed.")
