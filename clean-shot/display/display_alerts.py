#!/usr/bin/env python3
# display/display_alerts.py — Clean Shot: urgent visual + audio alert system
#
# 5 severity levels:
#   EMERGENCY  → screen flash + magenta box + 🚨  + 5 beeps + optional ack prompt
#   CRITICAL   → red bold box  + ⛔              + 3 beeps
#   WARNING    → yellow box    + ⚠️              + 1 beep
#   INFO       → cyan inline   + ℹ️              + no beep
#   LOW        → plain inline  + •               + no beep
#
# ANSI terminal flash:
#   EMERGENCY level triggers \033[?5h (reverse-video) strobe for xterm-compatible
#   terminals. Silently no-ops on terminals that don't support it.
#
# Acknowledgment system (opt-in):
#   config["alerts_require_ack"] = True  — EMERGENCY/CRITICAL banners pause up to
#   5 seconds for driver to press ENTER. Auto-dismisses on timeout. Only runs
#   when stdout is a tty (never blocks in scripts / tests).
#
# Beep platform dispatch (first working method wins):
#   Termux (Android) → termux-vibrate (haptic) + \a
#   Linux            → paplay bell.oga OR \a (BEL char)
#   Windows          → winsound.Beep(1000, 300)
#   macOS            → afplay Ping.aiff OR \a
#   Any              → print('\a') — always works in a terminal
#
# Integration:
#   alerts.py   → display_critical_alerts(alerts, config)
#   dot511.py   → display_dot511_critical(incidents, config)
#   hazards.py  → display_hazard_critical(hazards, config)
#   parking.py  → display_urgent_parking(runway, nearest_stop, config)
#   hos.py      → display_hos_critical(config)
#   All at once → check_and_display() master function

import os
import platform
import select
import shutil
import subprocess
import sys
import time

try:
    from colorama import Fore, Style, init as _colorama_init
    _colorama_init(autoreset=True)
    _COLORAMA = True
except ImportError:
    _COLORAMA = False

# ── Severity constants ────────────────────────────────────────────────────────

SEVERITIES = ("EMERGENCY", "CRITICAL", "WARNING", "INFO", "LOW")

# ── Color / style helpers ─────────────────────────────────────────────────────

def _c(color_str: str, text: str) -> str:
    """Apply colorama color if available, else return plain text."""
    if not _COLORAMA:
        return text
    return f"{color_str}{text}{Style.RESET_ALL}"


def severity_color(severity: str) -> str:
    """Return colorama color code for a severity level."""
    if not _COLORAMA:
        return ""
    return {
        "EMERGENCY": Fore.MAGENTA + Style.BRIGHT,
        "CRITICAL":  Fore.RED     + Style.BRIGHT,
        "WARNING":   Fore.YELLOW  + Style.BRIGHT,
        "INFO":      Fore.CYAN,
        "LOW":       "",
    }.get(severity.upper(), "")


def severity_icon(severity: str) -> str:
    """Return emoji icon for a severity level."""
    return {
        "EMERGENCY": "🚨",
        "CRITICAL":  "⛔",
        "WARNING":   "⚠️",
        "INFO":      "ℹ️",
        "LOW":       "•",
    }.get(severity.upper(), "•")


# ── Box drawing ───────────────────────────────────────────────────────────────

def _box(lines: list, severity: str = "CRITICAL", width: int = 0) -> str:
    """
    Build an ASCII box around the given lines.
    Width defaults to terminal width capped at 78.
    Returns the complete box as a single string (newlines included).
    """
    import re as _re
    term_w = min(shutil.get_terminal_size(fallback=(80, 24)).columns, 80)
    w      = width or term_w
    inner  = w - 4   # 2 border chars + 2 spaces padding

    color  = severity_color(severity)
    reset  = Style.RESET_ALL if _COLORAMA else ""

    # EMERGENCY: add blink to the color codes when colorama is available
    if severity.upper() == "EMERGENCY" and _COLORAMA:
        color = "\033[5m" + color   # ANSI blink prepended

    padded = []
    for line in lines:
        plain = _re.sub(r'\x1b\[[0-9;]*m', '', line)
        pad   = max(0, inner - len(plain))
        padded.append(f"║ {line}{' ' * pad} ║")

    bar    = "═" * (w - 2)
    result = [f"{color}╔{bar}╗{reset}"]
    for p in padded:
        result.append(f"{color}{p}{reset}")
    result.append(f"{color}╚{bar}╝{reset}")
    return "\n".join(result)


# ── ANSI terminal flash ───────────────────────────────────────────────────────

def flash_terminal(count: int = 2) -> None:
    """
    Flash the terminal screen using ANSI reverse-video strobe.
    Works in xterm-compatible terminals (most Linux/macOS terminals).
    Silently no-ops in terminals that don't support it or when not a tty.
    count: number of flash cycles (each cycle = on + off).
    """
    if not sys.stdout.isatty():
        return
    try:
        for _ in range(max(1, count)):
            sys.stdout.write("\033[?5h")   # reverse video ON
            sys.stdout.flush()
            time.sleep(0.12)
            sys.stdout.write("\033[?5l")   # reverse video OFF
            sys.stdout.flush()
            time.sleep(0.12)
    except Exception:
        pass


# ── Acknowledgment system ─────────────────────────────────────────────────────

def prompt_ack(timeout_s: float = 5.0, config: dict = None) -> bool:
    """
    Show an acknowledgment prompt and wait up to timeout_s seconds for ENTER.
    Returns True if driver acknowledged, False if timed out or ack not required.

    Only runs when:
      - stdout is a tty (never blocks in tests / scripts)
      - config["alerts_require_ack"] is True (opt-in, default False)

    This is intentionally permissive: if the driver doesn't press ENTER, the
    program continues automatically. Safety display never blocks indefinitely.
    """
    if not sys.stdout.isatty():
        return False
    if config and not config.get("alerts_require_ack", False):
        return False
    try:
        sys.stdout.write(
            f"  [ Driver — press ENTER to acknowledge  "
            f"(auto-dismiss in {int(timeout_s)}s) ] "
        )
        sys.stdout.flush()
        ready, _, _ = select.select([sys.stdin], [], [], float(timeout_s))
        if ready:
            sys.stdin.readline()
            return True
        sys.stdout.write("\n")
        sys.stdout.flush()
    except Exception:
        pass
    return False


# ── Platform-aware beep ───────────────────────────────────────────────────────

def _is_termux() -> bool:
    return bool(os.environ.get("TERMUX_VERSION") or shutil.which("termux-vibrate"))


def _beep_termux() -> None:
    try:
        subprocess.Popen(
            ["termux-vibrate", "-d", "400"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
    print("\a", end="", flush=True)


def _beep_linux() -> None:
    bell = "/usr/share/sounds/freedesktop/stereo/bell.oga"
    if shutil.which("paplay") and os.path.exists(bell):
        try:
            subprocess.Popen(
                ["paplay", bell],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            pass
    print("\a", end="", flush=True)


def _beep_windows() -> None:
    try:
        import winsound
        winsound.Beep(1000, 300)
        return
    except Exception:
        pass
    print("\a", end="", flush=True)


def _beep_macos() -> None:
    ping = "/System/Library/Sounds/Ping.aiff"
    if shutil.which("afplay") and os.path.exists(ping):
        try:
            subprocess.Popen(
                ["afplay", ping],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            pass
    print("\a", end="", flush=True)


def beep(count: int = 1, config: dict = None) -> None:
    """
    Emit an audible/haptic alert. Platform-dispatched, never crashes.
    count: number of beeps.  Silenced if config["tts_enabled"] is False.
    """
    if config and not config.get("tts_enabled", True):
        return

    plat = platform.system().lower()
    fn   = (
        _beep_termux  if _is_termux()       else
        _beep_linux   if plat == "linux"    else
        _beep_windows if plat == "windows"  else
        _beep_macos   if plat == "darwin"   else
        lambda: print("\a", end="", flush=True)
    )
    for _ in range(max(1, count)):
        fn()


def should_beep(severity: str) -> bool:
    """Return True if the severity level warrants an audio alert."""
    return severity.upper() in ("EMERGENCY", "CRITICAL", "WARNING")


def beep_count(severity: str) -> int:
    """Return number of beeps appropriate for a severity level."""
    return {
        "EMERGENCY": 5,
        "CRITICAL":  3,
        "WARNING":   1,
    }.get(severity.upper(), 0)


# ── Alert banner builders ─────────────────────────────────────────────────────

def flash_banner(message: str, severity: str = "CRITICAL") -> str:
    """
    Build a single-line alert banner string (no box).
    Used for inline warnings inside a larger display.
    """
    icon  = severity_icon(severity)
    color = severity_color(severity)
    reset = Style.RESET_ALL if _COLORAMA else ""
    return f"{color}{icon}  {severity.upper()} — {message}{reset}"


def build_critical_box(title: str, body: str = "",
                       severity: str = "CRITICAL") -> str:
    """
    Build a full-width critical alert box.
    title: short alert label  (e.g. "BLACK ICE AHEAD")
    body:  detail line        (e.g. "Smokey's reporting black ice — back it down")
    """
    icon   = severity_icon(severity)
    lines  = [f"{icon}  {severity.upper()} — {title}"]
    if body:
        lines.append(f"   {body}")
    return _box(lines, severity)


# ── Road alert display ────────────────────────────────────────────────────────

def display_critical_alert(alert: dict, config: dict = None) -> None:
    """
    Display a single EMERGENCY, CRITICAL, or WARNING road alert as a visual box.
    alert: dict from core.alerts.get_road_alerts() with keys type/severity/cb_voice
    """
    if not alert:
        return
    severity = alert.get("severity", "WARNING").upper()
    if severity not in ("EMERGENCY", "CRITICAL", "WARNING"):
        return

    atype  = alert.get("type", "").replace("_", " ").upper()
    voice  = alert.get("cb_voice", alert.get("description", ""))
    box    = build_critical_box(atype, voice, severity)
    print(box)

    if severity == "EMERGENCY":
        flash_terminal(3)

    if should_beep(severity):
        beep(beep_count(severity), config)

    prompt_ack(config=config)


def display_critical_alerts(alerts: list, config: dict = None) -> int:
    """
    Display all EMERGENCY, CRITICAL and WARNING alerts from alerts.py output.
    Returns count of alerts displayed.
    """
    if not alerts:
        return 0
    displayed = 0
    for alert in alerts:
        sev = alert.get("severity", "INFO").upper()
        if sev in ("EMERGENCY", "CRITICAL", "WARNING"):
            display_critical_alert(alert, config)
            displayed += 1
    return displayed


def display_dot511_critical(incidents: list, config: dict = None) -> int:
    """
    Display critical/high DOT/511 incidents as visual alert boxes.
    incidents: list from core.dot511.get_active_incidents()
    Returns count displayed.
    """
    if not incidents:
        return 0
    displayed = 0
    for inc in incidents:
        sev_str  = inc.get("severity", "low")
        tts_sev  = {"critical": "CRITICAL", "high": "WARNING"}.get(sev_str)
        if not tts_sev:
            continue
        itype = inc.get("type", "").replace("_", " ").upper()
        hw    = inc.get("highway", "")
        desc  = inc.get("description", "")
        title = f"{itype}{f'  [{hw}]' if hw else ''}"
        print(build_critical_box(title, desc, tts_sev))
        if should_beep(tts_sev):
            beep(beep_count(tts_sev), config)
        displayed += 1
    return displayed


def display_hazard_critical(hazards: list, config: dict = None) -> int:
    """
    Display critical community hazards as visual alert boxes.
    hazards: list from core.hazards.get_active_hazards()
    Returns count displayed.
    """
    if not hazards:
        return 0
    displayed = 0
    for h in hazards:
        sev_str = h.get("sev") or h.get("severity", "medium")
        if sev_str not in ("critical", "high"):
            continue
        htype    = (h.get("t") or h.get("hazard_type", "hazard")).replace("_", " ").upper()
        dist     = h.get("distance_mi")
        count    = h.get("driver_count", 1)
        dist_str  = f"{dist:.1f} mi ahead" if isinstance(dist, (int, float)) else ""
        count_str = f"{count} drivers reporting" if count > 1 else ""
        body     = "  ".join(filter(None, [dist_str, count_str]))
        tts_sev  = "CRITICAL" if sev_str == "critical" else "WARNING"
        print(build_critical_box(htype, body, tts_sev))
        if should_beep(tts_sev):
            beep(beep_count(tts_sev), config)
        displayed += 1
    return displayed


# ── Parking urgency banner ────────────────────────────────────────────────────

def display_urgent_parking(runway: dict, nearest_stop: dict = None,
                            config: dict = None) -> None:
    """
    Show a parking urgency banner when HOS runway is critical or urgent.
    runway: dict from core.parking.compute_runway()
    nearest_stop: dict from core.parking.find_recommended_stop() or None
    """
    if not runway:
        return
    level = runway.get("level", "normal")
    if level not in ("critical", "urgent", "warning"):
        return

    miles  = runway.get("miles", 0)
    mins   = runway.get("minutes", 0)

    sev_map = {"critical": "CRITICAL", "urgent": "WARNING", "warning": "INFO"}
    tts_sev = sev_map[level]

    if level == "critical":
        title = f"YOU MUST STOP WITHIN {miles:.0f} MILES"
    elif level == "urgent":
        title = f"FIND PARKING — {miles:.0f} MI / {mins} MIN REMAINING"
    else:
        title = f"START LOOKING — {miles:.0f} MI RUNWAY REMAINING"

    body = ""
    if nearest_stop:
        name  = nearest_stop.get("name", "Unknown")
        hw    = nearest_stop.get("highway", "")
        exit_ = nearest_stop.get("exit", "")
        dist  = nearest_stop.get("distance_mi", "?")
        hw_str = f"{hw} Exit {exit_}" if hw and exit_ else hw
        body = f"{name}  ·  {hw_str}  ·  {dist} mi"

    print(build_critical_box(title, body, tts_sev))
    if should_beep(tts_sev):
        beep(beep_count(tts_sev), config)


# ── HOS urgency banner ────────────────────────────────────────────────────────

def display_hos_critical(config: dict = None) -> int:
    """
    Show a HOS urgency banner when hours-of-service are in an urgent/critical state.
    Reads live HOS status from config via core.hos.get_hos_status().
    Returns 1 if a banner was shown, 0 otherwise.
    """
    try:
        from core.hos import get_hos_status
    except ImportError:
        return 0

    if not config:
        return 0

    status = get_hos_status(config)
    level  = status.get("level", "normal")
    if level not in ("urgent", "critical"):
        return 0

    effective = status["effective_remaining_min"]
    h = effective // 60
    m = effective % 60
    time_str = f"{h}h {m:02d}m" if h else f"{m} min"

    if level == "critical":
        tts_sev = "EMERGENCY" if effective <= 15 else "CRITICAL"
        title   = f"HOS EXPIRING — {time_str} REMAINING — PULL OVER NOW"
    else:
        tts_sev = "WARNING"
        title   = f"HOS — {time_str} REMAINING — START LOOKING FOR PARKING"

    needs_brk = status.get("needs_break", False)
    body = ""
    if needs_brk:
        ovd = status.get("break_overdue_min", 0)
        body = f"30-MIN BREAK REQUIRED  ({ovd:.0f} min overdue)" if ovd > 0 else "30-MIN BREAK REQUIRED"

    print(build_critical_box(title, body, tts_sev))

    if tts_sev == "EMERGENCY":
        flash_terminal(3)

    if should_beep(tts_sev):
        beep(beep_count(tts_sev), config)

    prompt_ack(config=config)
    return 1


# ── Master function ───────────────────────────────────────────────────────────

def check_and_display(
    alerts: list = None,
    incidents: list = None,
    hazards: list = None,
    runway: dict = None,
    nearest_stop: dict = None,
    config: dict = None,
    include_hos: bool = False,
) -> bool:
    """
    Master alert display function. Called by core/weather.py display loop.

    Checks all data sources for critical/urgent conditions and displays
    visual banners + beeps + optional ack for anything requiring driver attention.

    Args:
        alerts       : from core.alerts.get_road_alerts()
        incidents    : from core.dot511.get_active_incidents()
        hazards      : from core.hazards.get_active_hazards()
        runway       : from core.parking.compute_runway()
        nearest_stop : from core.parking.find_recommended_stop()
        config       : driver config dict
        include_hos  : when True, also checks HOS status from config

    Returns True if any critical/urgent condition was displayed.
    """
    if config is None:
        config = {}

    displayed = 0

    # 1. HOS urgency — highest priority (legal/safety)
    if include_hos:
        displayed += display_hos_critical(config)

    # 2. Parking urgency — show before weather alerts (time-critical)
    if runway and runway.get("level") in ("critical", "urgent"):
        display_urgent_parking(runway, nearest_stop, config)
        displayed += 1

    # 3. Road alerts (from weather detectors)
    if alerts:
        displayed += display_critical_alerts(alerts, config)

    # 4. DOT/511 critical incidents
    if incidents:
        displayed += display_dot511_critical(incidents, config)

    # 5. Community hazards
    if hazards:
        displayed += display_hazard_critical(hazards, config)

    return displayed > 0
