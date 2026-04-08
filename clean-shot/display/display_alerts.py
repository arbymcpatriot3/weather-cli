#!/usr/bin/env python3
# display/display_alerts.py — Clean Shot: urgent visual + audio alert system
#
# Handles CRITICAL and WARNING visual banners + platform-aware beep.
# Called by core/weather.py main display loop and by individual modules
# when a condition escalates to CRITICAL.
#
# Visual design:
#   CRITICAL  → red bold box with ⛔, beep 3×
#   WARNING   → yellow box with ⚠, beep 1×
#   INFO      → plain print, no beep
#
# Beep platform dispatch (first working method wins):
#   Termux (Android) → termux-vibrate (haptic) + \a
#   Linux            → paplay bell.oga OR \a (BEL char)
#   Windows          → winsound.Beep(1000, 300)
#   macOS            → afplay Ping.aiff OR \a
#   Any              → print('\a') — always works in a terminal
#
# Integration:
#   alerts.py   → pass output of get_road_alerts() to display_road_alerts()
#   dot511.py   → pass output of get_active_incidents() to display_dot511_critical()
#   hazards.py  → pass output of get_active_hazards() to display_hazard_critical()
#   parking.py  → pass runway dict + nearest stop to display_urgent_parking()
#   All at once → check_and_display() master function

import os
import platform
import shutil
import subprocess
import sys

try:
    from colorama import Fore, Style, init as _colorama_init
    _colorama_init(autoreset=True)
    _COLORAMA = True
except ImportError:
    _COLORAMA = False

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
        "CRITICAL": Fore.RED + Style.BRIGHT,
        "WARNING":  Fore.YELLOW + Style.BRIGHT,
        "INFO":     Fore.CYAN,
    }.get(severity.upper(), "")


def severity_icon(severity: str) -> str:
    """Return emoji icon for a severity level."""
    return {
        "CRITICAL": "⛔",
        "WARNING":  "⚠️",
        "INFO":     "ℹ️",
    }.get(severity.upper(), "•")


# ── Box drawing ────────────────────────────────────────────────────────────────

def _box(lines: list[str], severity: str = "CRITICAL", width: int = 0) -> str:
    """
    Build an ASCII box around the given lines.
    Width defaults to terminal width capped at 78.
    Returns the complete box as a single string (newlines included).
    """
    term_w = min(shutil.get_terminal_size(fallback=(80, 24)).columns, 80)
    w      = width or term_w
    inner  = w - 4   # 2 border chars + 2 spaces padding

    color  = severity_color(severity)
    reset  = Style.RESET_ALL if _COLORAMA else ""

    padded = []
    for line in lines:
        # Strip existing ANSI codes for length measurement
        plain = line
        if _COLORAMA:
            import re
            plain = re.sub(r'\x1b\[[0-9;]*m', '', line)
        pad   = max(0, inner - len(plain))
        padded.append(f"║ {line}{' ' * pad} ║")

    bar    = "═" * (w - 2)
    result = [f"{color}╔{bar}╗{reset}"]
    for p in padded:
        result.append(f"{color}{p}{reset}")
    result.append(f"{color}╚{bar}╝{reset}")
    return "\n".join(result)


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
    # Try paplay with freedesktop bell sound; fall back to BEL
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
    count: number of beeps (1 for WARNING, 3 for CRITICAL).
    """
    if config and not config.get("tts_enabled", True):
        return   # respect audio-off setting

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
    return severity.upper() in ("CRITICAL", "WARNING")


def beep_count(severity: str) -> int:
    """Return number of beeps appropriate for a severity level."""
    return {"CRITICAL": 3, "WARNING": 1}.get(severity.upper(), 0)


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
    Display a single CRITICAL or WARNING road alert as a visual box.
    alert: dict from core.alerts.get_road_alerts() with keys type/severity/cb_voice
    """
    if not alert:
        return
    severity = alert.get("severity", "WARNING").upper()
    if severity not in ("CRITICAL", "WARNING"):
        return

    atype  = alert.get("type", "").replace("_", " ").upper()
    voice  = alert.get("cb_voice", alert.get("description", ""))
    print(build_critical_box(atype, voice, severity))

    if should_beep(severity):
        beep(beep_count(severity), config)


def display_critical_alerts(alerts: list, config: dict = None) -> int:
    """
    Display all CRITICAL and WARNING alerts from alerts.py output.
    Returns count of alerts displayed.
    """
    if not alerts:
        return 0
    displayed = 0
    for alert in alerts:
        sev = alert.get("severity", "INFO").upper()
        if sev in ("CRITICAL", "WARNING"):
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
        htype   = (h.get("t") or h.get("hazard_type", "hazard")).replace("_", " ").upper()
        dist    = h.get("distance_mi")
        count   = h.get("driver_count", 1)
        dist_str = f"{dist:.1f} mi ahead" if isinstance(dist, (int, float)) else ""
        count_str = f"{count} drivers reporting" if count > 1 else ""
        body    = "  ".join(filter(None, [dist_str, count_str]))
        tts_sev = "CRITICAL" if sev_str == "critical" else "WARNING"
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

    miles = runway.get("miles", 0)
    mins  = runway.get("minutes", 0)

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


# ── Master function ───────────────────────────────────────────────────────────

def check_and_display(
    alerts: list = None,
    incidents: list = None,
    hazards: list = None,
    runway: dict = None,
    nearest_stop: dict = None,
    config: dict = None,
) -> bool:
    """
    Master alert display function. Called by core/weather.py display loop.

    Checks all data sources for critical/urgent conditions and displays
    visual banners + beeps for anything requiring driver attention.

    Args:
        alerts       : from core.alerts.get_road_alerts()
        incidents    : from core.dot511.get_active_incidents()
        hazards      : from core.hazards.get_active_hazards()
        runway       : from core.parking.compute_runway()
        nearest_stop : from core.parking.find_recommended_stop()
        config       : driver config dict

    Returns True if any critical/urgent condition was displayed.
    """
    if config is None:
        config = {}

    displayed = 0

    # 1. Parking urgency — show first (time-critical)
    if runway and runway.get("level") in ("critical", "urgent"):
        display_urgent_parking(runway, nearest_stop, config)
        displayed += 1

    # 2. Road alerts (from weather detectors)
    if alerts:
        displayed += display_critical_alerts(alerts, config)

    # 3. DOT/511 critical incidents
    if incidents:
        displayed += display_dot511_critical(incidents, config)

    # 4. Community hazards
    if hazards:
        displayed += display_hazard_critical(hazards, config)

    return displayed > 0
