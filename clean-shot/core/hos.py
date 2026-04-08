#!/usr/bin/env python3
# core/hos.py — Clean Shot: HOS Guardian (Hours of Service)
# Tier: Solo Pro+  (has_feature config, "hos_guardian")
#
# DISCLAIMER: This is an advisory tool only. It does NOT replace a certified
# ELD (Electronic Logging Device). Drivers remain responsible for FMCSA
# compliance. Clean Shot / Blue Collar Nation LLC assumes no liability for
# HOS violations.
#
# FMCSA Property-Carrying CMV Rules implemented:
#   11-hour driving limit  — max driving after 10 consecutive hours off duty
#   14-hour on-duty window — hard wall clock; cannot drive after 14h from duty start
#   30-minute break        — required if 8+ hours of driving without a 30-min break
#   60/70-hour weekly      — 60h in 7 days OR 70h in 8 days (driver selects cycle)
#   10-hour reset          — 10 consecutive hours off duty resets 11h + 14h window
#
# Sleeper berth split provisions NOT implemented (Phase 2).
# Adverse driving conditions extension NOT implemented (advisory flag only).
#
# State model:
#   All HOS state lives in the config dict and is persisted by save_config().
#   Key fields (all prefixed "hos_"):
#
#     hos_session_start_ts   — unix ts: when current 14-h duty window started
#     hos_drive_elapsed_min  — float: accumulated drive minutes this window
#     hos_drive_start_ts     — unix ts: start of current drive segment (None = parked)
#     hos_break_drive_min    — float: drive minutes since last qualifying 30-min break
#     hos_is_driving         — bool: currently driving?
#     hos_is_on_duty         — bool: currently on duty?
#     hos_7day_duty_min      — float: total on-duty minutes in rolling 7/8-day period
#     hos_cycle              — "60_7" | "70_8"
#
#   Derived (written into config by get_hos_status so parking.py always has fresh data):
#     hos_drive_remaining_min — effective drivable minutes (min of drive + duty remaining)
#
# Integration:
#   core/parking.py  reads config["hos_drive_remaining_min"]  for runway calc
#   core/weather.py  calls display_hos_status() in the full/watch display loop
#   display/glance.py (future) reads status dict for compact HOS bar

import shutil
import time

from core.subscription import has_feature

# ── FMCSA constants ───────────────────────────────────────────────────────────

HOS_DRIVE_LIMIT_MIN    = 660    # 11 hours — max driving per reset window
HOS_DUTY_LIMIT_MIN     = 840    # 14 hours — hard on-duty wall clock from session start
HOS_BREAK_TRIGGER_MIN  = 480    # 8 hours driving without a break → break required
HOS_BREAK_REQUIRED_MIN = 30     # minimum break duration to reset the 8h counter
HOS_RESET_MIN          = 600    # 10 consecutive hours off duty → full reset
HOS_34H_RESTART_MIN    = 2040   # 34-hour restart → resets weekly cycle
HOS_WEEKLY_60_MIN      = 3600   # 60 hours in 7 consecutive days
HOS_WEEKLY_70_MIN      = 4200   # 70 hours in 8 consecutive days

# TTS thresholds: (effective_remaining_min, tts_severity, alert_type)
# "Effective" = min(drive_remaining, duty_remaining)
_HOS_THRESHOLDS = [
    (120, "INFO",     "parking_ahead"),   # 2 h remaining — start looking for parking
    ( 60, "WARNING",  "parking_ahead"),   # 1 h remaining — get serious
    ( 30, "WARNING",  "hos_warning"),     # 30 min        — need to stop soon
    ( 15, "CRITICAL", "hos_warning"),     # 15 min        — pull over now
]

# ── Mockable time source (override in tests) ──────────────────────────────────

_time_fn = time.time   # tests can monkey-patch this


def _now() -> float:
    return _time_fn()


# ── Config field defaults (applied lazily by _ensure_fields) ─────────────────

_HOS_DEFAULTS = {
    "hos_session_start_ts":    None,
    "hos_drive_elapsed_min":   0.0,
    "hos_drive_start_ts":      None,
    "hos_break_drive_min":     0.0,
    "hos_is_driving":          False,
    "hos_is_on_duty":          False,
    "hos_7day_duty_min":       0.0,
    "hos_cycle":               "70_8",    # most US long-haul carriers use 70/8
    # Written by get_hos_status() for parking.py
    "hos_drive_remaining_min": float(HOS_DRIVE_LIMIT_MIN),
}


def _ensure_fields(config: dict) -> dict:
    """Back-fill any missing HOS config fields with defaults."""
    for k, v in _HOS_DEFAULTS.items():
        config.setdefault(k, v)
    return config


# ── Live elapsed helpers ──────────────────────────────────────────────────────

def _live_drive_min(config: dict) -> float:
    """
    Total drive minutes this window including the currently-running segment.
    Capped at HOS_DRIVE_LIMIT_MIN to prevent display overflow.
    """
    _ensure_fields(config)
    elapsed = float(config["hos_drive_elapsed_min"])
    if config["hos_is_driving"] and config["hos_drive_start_ts"]:
        elapsed += (_now() - config["hos_drive_start_ts"]) / 60.0
    return min(elapsed, HOS_DRIVE_LIMIT_MIN)


def _live_break_drive_min(config: dict) -> float:
    """
    Drive minutes since last qualifying break, including current segment.
    """
    _ensure_fields(config)
    elapsed = float(config["hos_break_drive_min"])
    if config["hos_is_driving"] and config["hos_drive_start_ts"]:
        elapsed += (_now() - config["hos_drive_start_ts"]) / 60.0
    return elapsed


def _live_duty_elapsed_min(config: dict) -> float:
    """
    Minutes elapsed in the current 14-hour duty window (wall clock).
    Returns 0 if no session has started.
    """
    _ensure_fields(config)
    if not config["hos_session_start_ts"]:
        return 0.0
    elapsed = (_now() - config["hos_session_start_ts"]) / 60.0
    return min(elapsed, HOS_DUTY_LIMIT_MIN)


# ── Core status function ──────────────────────────────────────────────────────

def get_hos_status(config: dict) -> dict:
    """
    Compute live HOS status from config state.

    Always writes config["hos_drive_remaining_min"] as a side effect so that
    core/parking.py gets fresh data without an extra call.

    Returns:
        drive_remaining_min     : int   — drivable minutes remaining in 11-h window
        duty_remaining_min      : int   — minutes before 14-h wall clock expires
        effective_remaining_min : int   — min(drive, duty) — true limit
        break_drive_min         : float — drive mins since last qualifying break
        needs_break             : bool  — 8-h break rule triggered?
        break_overdue_min       : float — how far past 8h (0 if not needed)
        violation_risk          : bool  — effective remaining ≤ 30 min
        violation_imminent      : bool  — effective remaining ≤ 15 min
        weekly_remaining_min    : float — remaining in 60/70-h weekly window
        is_driving              : bool
        is_on_duty              : bool
        level                   : str  — "normal" | "warning" | "urgent" | "critical"
        has_session             : bool — True if a duty window is active
    """
    _ensure_fields(config)

    drive_elapsed = _live_drive_min(config)
    break_drive   = _live_break_drive_min(config)
    duty_elapsed  = _live_duty_elapsed_min(config)

    drive_remaining = max(0, int(HOS_DRIVE_LIMIT_MIN - drive_elapsed))
    duty_remaining  = max(0, int(HOS_DUTY_LIMIT_MIN  - duty_elapsed))

    # If no duty session started yet, the 14h wall hasn't started ticking
    if config["hos_session_start_ts"] is None:
        effective = drive_remaining
    else:
        effective = min(drive_remaining, duty_remaining)

    needs_break   = break_drive >= HOS_BREAK_TRIGGER_MIN
    break_overdue = max(0.0, break_drive - HOS_BREAK_TRIGGER_MIN)

    cycle            = config.get("hos_cycle", "70_8")
    weekly_limit     = HOS_WEEKLY_70_MIN if cycle == "70_8" else HOS_WEEKLY_60_MIN
    weekly_remaining = max(0.0, weekly_limit - float(config.get("hos_7day_duty_min", 0.0)))

    level = _urgency_level(effective)

    # Write parking.py feed key
    config["hos_drive_remaining_min"] = float(effective)

    return {
        "drive_remaining_min":     drive_remaining,
        "duty_remaining_min":      duty_remaining,
        "effective_remaining_min": effective,
        "break_drive_min":         round(break_drive, 1),
        "needs_break":             needs_break,
        "break_overdue_min":       round(break_overdue, 1),
        "violation_risk":          effective <= 30,
        "violation_imminent":      effective <= 15,
        "weekly_remaining_min":    round(weekly_remaining, 1),
        "is_driving":              bool(config["hos_is_driving"]),
        "is_on_duty":              bool(config["hos_is_on_duty"]),
        "level":                   level,
        "has_session":             config["hos_session_start_ts"] is not None,
    }


def _urgency_level(effective_remaining_min: int) -> str:
    """Map effective remaining minutes to a display urgency level."""
    if effective_remaining_min <= 15:
        return "critical"
    if effective_remaining_min <= 30:
        return "urgent"
    if effective_remaining_min <= 60:
        return "warning"
    return "normal"


# ── Session control ───────────────────────────────────────────────────────────

def start_duty(config: dict) -> dict:
    """
    Mark the start of an on-duty period (after 10-hour reset).
    Starts the 14-hour duty window if one is not already active.
    Call this when the driver clocks in for a new shift.
    """
    _ensure_fields(config)
    config["hos_is_on_duty"] = True
    if config["hos_session_start_ts"] is None:
        config["hos_session_start_ts"] = _now()
    return config


def end_duty(config: dict) -> dict:
    """
    Mark the driver as off duty (parked for the night, etc.).
    Does NOT reset accumulated drive time — only a full reset_hos() does that.
    """
    _ensure_fields(config)
    if config["hos_is_driving"]:
        stop_drive(config)
    config["hos_is_on_duty"] = False
    return config


def start_drive(config: dict) -> dict:
    """
    Mark the start of a driving segment.
    Automatically starts duty window if not already running.
    """
    _ensure_fields(config)
    if not config["hos_is_on_duty"] or config["hos_session_start_ts"] is None:
        start_duty(config)
    if not config["hos_is_driving"]:
        config["hos_is_driving"]     = True
        config["hos_drive_start_ts"] = _now()
    return config


def stop_drive(config: dict) -> dict:
    """
    Mark the end of a driving segment.
    Accumulates elapsed drive time and break-drive counter.
    Driver remains on duty until end_duty() is called.
    """
    _ensure_fields(config)
    if config["hos_is_driving"] and config["hos_drive_start_ts"]:
        segment_min = (_now() - config["hos_drive_start_ts"]) / 60.0
        config["hos_drive_elapsed_min"] = (
            float(config["hos_drive_elapsed_min"]) + segment_min
        )
        config["hos_break_drive_min"] = (
            float(config["hos_break_drive_min"]) + segment_min
        )
    config["hos_is_driving"]     = False
    config["hos_drive_start_ts"] = None
    return config


def take_break(config: dict) -> dict:
    """
    Record a qualifying 30-minute (or longer) off-duty break.
    Resets the break_drive_min counter. Does NOT reset the 11-h or 14-h window.
    Call this after the driver has been off duty for >= 30 minutes.
    """
    _ensure_fields(config)
    if config["hos_is_driving"]:
        stop_drive(config)
    config["hos_break_drive_min"] = 0.0
    return config


def reset_hos(config: dict) -> dict:
    """
    Full HOS reset after 10 consecutive hours off duty.
    Clears the 11-h driving window, the 14-h duty window, and the break counter.
    Call this when the driver has completed a 10-hour off-duty period.
    """
    _ensure_fields(config)
    if config["hos_is_driving"]:
        stop_drive(config)
    config["hos_session_start_ts"]    = None
    config["hos_drive_elapsed_min"]   = 0.0
    config["hos_drive_start_ts"]      = None
    config["hos_break_drive_min"]     = 0.0
    config["hos_is_driving"]          = False
    config["hos_is_on_duty"]          = False
    config["hos_drive_remaining_min"] = float(HOS_DRIVE_LIMIT_MIN)
    return config


def update_elapsed(config: dict) -> dict:
    """
    Refresh config["hos_drive_remaining_min"] without changing session state.
    Called by core/weather.py watch loop to keep parking.py feed current.
    """
    _ensure_fields(config)
    get_hos_status(config)   # side effect writes hos_drive_remaining_min
    return config


# ── Break helpers ─────────────────────────────────────────────────────────────

def needs_break(config: dict) -> bool:
    """True if 8 or more hours of driving have elapsed since last qualifying break."""
    return _live_break_drive_min(config) >= HOS_BREAK_TRIGGER_MIN


def minutes_until_break_required(config: dict) -> float:
    """
    Minutes of driving remaining before the 30-min break becomes mandatory.
    Returns 0 if break is already required.
    """
    return max(0.0, HOS_BREAK_TRIGGER_MIN - _live_break_drive_min(config))


# ── Weekly / cycle helpers ────────────────────────────────────────────────────

def add_duty_to_weekly(config: dict, minutes: float) -> dict:
    """
    Add on-duty minutes to the rolling 7/8-day counter.
    Call this at end of each duty day. Values self-reported — advisory only.
    """
    _ensure_fields(config)
    config["hos_7day_duty_min"] = float(config.get("hos_7day_duty_min", 0.0)) + minutes
    return config


def reset_weekly(config: dict) -> dict:
    """Reset the weekly on-duty counter (after 34-hour restart or new cycle)."""
    _ensure_fields(config)
    config["hos_7day_duty_min"] = 0.0
    return config


def get_weekly_remaining(config: dict) -> float:
    """Minutes remaining in the 60-h/7-day or 70-h/8-day weekly window."""
    _ensure_fields(config)
    cycle = config.get("hos_cycle", "70_8")
    limit = HOS_WEEKLY_70_MIN if cycle == "70_8" else HOS_WEEKLY_60_MIN
    return max(0.0, limit - float(config.get("hos_7day_duty_min", 0.0)))


# ── Threshold check (pure — no side effects) ──────────────────────────────────

def check_hos_thresholds(config: dict) -> list:
    """
    Return list of threshold tuples the driver has currently crossed.
    Pure function — does not fire TTS or mutate state.
    Caller (announce_hos) handles speaking + threshold tracking.

    Returns list of (minutes_remaining, severity, alert_type) tuples
    for each threshold whose limit >= effective_remaining_min.
    """
    status    = get_hos_status(config)
    effective = status["effective_remaining_min"]
    return [
        (thresh_min, severity, alert_type)
        for (thresh_min, severity, alert_type) in _HOS_THRESHOLDS
        if effective <= thresh_min
    ]


# ── Module-level threshold tracking (fires once per trip per threshold) ───────

_announced: set = set()   # threshold minutes already announced this trip


def announce_hos(config: dict) -> int:
    """
    Speak any newly-crossed HOS thresholds via TTS (fires once per threshold).
    Silently skips if TTS not available or feature not enabled.
    Returns count of new announcements made.
    """
    _ensure_fields(config)
    if not has_feature(config, "hos_guardian"):
        return 0

    status    = get_hos_status(config)
    effective = status["effective_remaining_min"]
    announced = 0

    try:
        from core.tts import speak_alert
    except ImportError:
        return 0

    for (thresh_min, severity, alert_type) in _HOS_THRESHOLDS:
        if effective <= thresh_min and thresh_min not in _announced:
            speak_alert(alert_type, severity, config)
            _announced.add(thresh_min)
            announced += 1

    return announced


def reset_announcements() -> None:
    """
    Clear the per-trip announcement tracking set.
    Call this at the start of each new trip / drive session.
    """
    global _announced
    _announced = set()


# ── Display ───────────────────────────────────────────────────────────────────

def _w(config=None) -> int:
    """Effective display width for HOS module."""
    override = (config or {}).get("display_width_override")
    if override and isinstance(override, int) and 20 <= override <= 300:
        return override
    return max(36, shutil.get_terminal_size(fallback=(80, 24)).columns)


def _mode(w: int) -> str:
    if w < 40: return "ultra_compact"
    if w < 60: return "compact"
    if w < 80: return "standard"
    return "full"


def format_hos_str(status: dict, config: dict = None) -> str:
    """
    Build a width-aware HOS summary string.
    Full:    "HOS  Drive: 6h 30m  Duty: 9h 15m  Effective: 6h 30m  [ADVISORY ONLY]"
    Compact: "HOS Drv:6h30m Dty:9h15m Eff:6h30m"
    Ultra:   "HOS 6h30m"
    """
    def _fmt(minutes: int) -> str:
        h = int(minutes) // 60
        m = int(minutes) % 60
        return f"{h}h {m:02d}m"

    w    = _w(config)
    mode = _mode(w)

    drive_str = _fmt(status["drive_remaining_min"])
    duty_str  = _fmt(status["duty_remaining_min"])
    eff_str   = _fmt(status["effective_remaining_min"])
    brk_flag  = " ⚠BRK" if status["needs_break"] else ""

    if mode == "ultra_compact":
        return f"HOS {eff_str}{brk_flag}"
    if mode == "compact":
        return f"HOS Drv:{drive_str} Dty:{duty_str} Eff:{eff_str}{brk_flag}"
    return (
        f"HOS  Drive: {drive_str}  Duty: {duty_str}  "
        f"Effective: {eff_str}{'  ⚠ BREAK REQUIRED' if status['needs_break'] else ''}  [ADVISORY ONLY]"
    )


def display_hos_status(config: dict) -> None:
    """
    Width-responsive HOS status block.
    Gated: solo_pro+ only. Prints an upgrade prompt for free tier.
    """
    if not has_feature(config, "hos_guardian"):
        print("  HOS Guardian: Solo Pro+ feature — upgrade to enable")
        return

    w      = _w(config)
    mode   = _mode(w)
    sep    = "─" * w
    status = get_hos_status(config)

    def _fmt(minutes: int) -> str:
        h = int(minutes) // 60
        m = int(minutes) % 60
        return f"{h}h {m:02d}m"

    level_icon = {
        "normal":   "✅",
        "warning":  "⚠️",
        "urgent":   "🔶",
        "critical": "⛔",
    }.get(status["level"], "•")

    print()

    if mode == "ultra_compact":
        brk = " BRK!" if status["needs_break"] else ""
        eff = _fmt(status["effective_remaining_min"])
        print(f"{level_icon}HOS {eff}{brk}"[:w])
        if status["violation_imminent"]:
            print("⛔PULL OVER NOW"[:w])
        elif status["violation_risk"]:
            print("⚠ FIND PARKING"[:w])
        return

    print(sep)

    if mode == "compact":
        print(f"  {level_icon} HOS (Advisory)")
        print(f"  Drv: {_fmt(status['drive_remaining_min'])}  Dty: {_fmt(status['duty_remaining_min'])}")
        print(f"  Effective: {_fmt(status['effective_remaining_min'])}")
        if status["needs_break"]:
            print(f"  ⚠ BREAK REQUIRED ({status['break_overdue_min']:.0f}min overdue)")
        if status["violation_imminent"]:
            print("  ⛔ PULL OVER — LIMIT IMMINENT")
        elif status["violation_risk"]:
            print("  ⚠ FIND PARKING NOW")
    else:
        print(f"  {level_icon}  HOS STATUS  (Advisory Only — Not an ELD)")
        print(f"  {'─' * min(44, w - 2)}")
        print(f"  Drive remaining   : {_fmt(status['drive_remaining_min'])} of 11h")
        print(f"  Duty window left  : {_fmt(status['duty_remaining_min'])} of 14h")
        print(f"  Effective limit   : {_fmt(status['effective_remaining_min'])}")

        if status["needs_break"]:
            print(f"  ⚠  BREAK REQUIRED — {status['break_overdue_min']:.0f} min overdue")
        else:
            bfm = minutes_until_break_required(config)
            print(f"  Next break req'd in: {_fmt(int(bfm))} of driving")

        wr    = status["weekly_remaining_min"]
        cycle = config.get("hos_cycle", "70_8")
        wlbl  = "70h/8-day" if cycle == "70_8" else "60h/7-day"
        print(f"  Weekly ({wlbl}): {_fmt(int(wr))} remaining")

        if status["is_driving"]:
            state_str = "Driving"
        elif status["is_on_duty"]:
            state_str = "On Duty (Not Driving)"
        else:
            state_str = "Off Duty"
        print(f"  Status            : {state_str}")

        if status["violation_imminent"]:
            print()
            print("  ⛔ PULL OVER — HOS LIMIT IMMINENT")
        elif status["violation_risk"]:
            print()
            print("  ⚠  START LOOKING FOR PARKING — 30 MIN OR LESS")

    print(sep)
