#!/usr/bin/env python3
# core/tts.py — Clean Shot: platform-agnostic TTS engine
#
# Platform dispatch:
#   Linux    → pyttsx3 (offline)                    pip install pyttsx3
#   Windows  → Windows SAPI (built-in)              no install needed
#   iOS      → AVSpeechSynthesizer bridge           via Pythonista/Pyto
#   Termux   → termux-tts-speak (Android)           pkg install termux-api
#   macOS    → /usr/bin/say fallback
#   Any      → terminal print fallback              always works
#
# Severity routing:
#   CRITICAL  — interrupts immediately; bypasses quiet hours by default
#   WARNING   — queued for next safe pause (when parked or flush_queue() called)
#   INFO      — spoken only on explicit request; never auto-fires
#
# Smart behaviors:
#   Speed-aware      — skips speech while driver is moving (WARNING/INFO only)
#   Repeat suppress  — won't re-speak same alert within suppress window (default 30 min)
#   Distance trigger — escalates severity as driver closes on hazard (50/20/5 mi)
#   Bluetooth route  — detects BT audio sink on Linux; future hook for other platforms
#   Quiet hours      — silences WARNING/INFO between configurable hours
#   Language-aware   — English → CB radio strings; other langs → t() translated strings
#
# Zero bytes of network traffic. All logic is local.

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, time as dtime

from claude.prompts import cb_voice_alert, _CB_VOICE_ALERTS
from core.i18n.translator import t, set_language

# ── Constants ─────────────────────────────────────────────────────────────────

WAKE_PHRASE            = "Hey Clean Shot"   # Phase 2: full voice recognition
REPEAT_SUPPRESS_SECS   = 1800              # 30 minutes default
CRITICAL_BYPASS_QUIET  = True              # CRITICAL always speaks, even in quiet hours

# Distance trigger thresholds (miles ahead)
DIST_INFO_MI      = 50.0
DIST_WARNING_MI   = 20.0
DIST_CRITICAL_MI  = 5.0

# Queue priority (lower = higher priority)
_PRIORITY = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}

# All 14 supported alert types (from claude/prompts.py)
ALL_ALERT_TYPES = tuple(_CB_VOICE_ALERTS.keys())


# ── Module-level state (thread-safe) ──────────────────────────────────────────

# Keyed by alert_type → {"time": float, "text_hash": str}
# Storing text_hash lets us re-alert when the same type escalates to worse text
# (e.g. diesel_gel watch → diesel_gel CRITICAL = different string = re-alert).
_spoken:      dict  = {}    # { alert_type: {"time": float, "text_hash": str} }
_queue:       list  = []    # [ (priority, alert_type, text, timestamp) ]
_spoken_lock        = threading.Lock()
_queue_lock         = threading.Lock()

_wake_callback      = None  # Phase 2 voice recognition hook

# Show the pyttsx3-missing warning only once per session (not on every alert)
_pyttsx3_warned:    bool = False


# ── Platform detection ────────────────────────────────────────────────────────

def _is_termux() -> bool:
    """Return True when running inside Termux (Android)."""
    return bool(os.environ.get("TERMUX_VERSION")
                or shutil.which("termux-tts-speak"))


def _is_bt_connected() -> bool:
    """
    Return True if a Bluetooth audio sink is active.
    Linux only (via pactl). Other platforms: always False for now.
    """
    if platform.system().lower() != "linux":
        return False
    try:
        r = subprocess.run(
            ["pactl", "list", "short", "sinks"],
            capture_output=True, text=True, timeout=2,
        )
        return "bluez" in r.stdout.lower()
    except Exception:
        return False


# ── Platform dispatch ─────────────────────────────────────────────────────────

def _dispatch(text: str, config: dict) -> bool:
    """
    Send text to the appropriate TTS engine.
    Returns True if speech was dispatched, False on failure.
    Falls back through the chain until something works.
    """
    plat = platform.system().lower()

    # ── Termux (Android) ──────────────────────────────────────────────────────
    if _is_termux():
        try:
            lang = config.get("language", "en")
            subprocess.Popen(
                ["termux-tts-speak", "-l", lang, text],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            pass

    # ── Linux — pyttsx3 (fully offline) ──────────────────────────────────────
    if plat == "linux":
        global _pyttsx3_warned
        try:
            import pyttsx3 as _pyttsx3_check  # noqa: F401
            del _pyttsx3_check
        except ImportError:
            if not _pyttsx3_warned:
                _pyttsx3_warned = True
                print(
                    "\n  ⚠️  Voice alerts not available — pyttsx3 not installed"
                    "\n     Fix: sudo apt-get install -y espeak-ng libespeak-ng1"
                    "\n          pip3 install pyttsx3 --break-system-packages"
                    "\n     Or:  cleanshot settings tts off\n"
                )
            # Fall through to terminal print fallback
        else:
            try:
                from platforms.linux.tts_linux import speak_linux
                if speak_linux(text):
                    return True
            except Exception:
                pass

    # ── Windows — SAPI (built-in) ─────────────────────────────────────────────
    elif plat == "windows":
        try:
            from platforms.windows.tts_windows import speak_windows
            if speak_windows(text):
                return True
        except Exception:
            pass

    # ── macOS / iOS — say command or AVSpeechSynthesizer ─────────────────────
    elif plat == "darwin":
        try:
            from platforms.ios.tts_ios import speak_ios
            if speak_ios(text):
                return True
        except Exception:
            pass
        try:
            subprocess.Popen(["say", text],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            pass

    # ── Terminal fallback — always works ─────────────────────────────────────
    print(f"\n[Clean Shot] {text}\n", flush=True)
    return True   # print is never False


# ── Smart behavior helpers ────────────────────────────────────────────────────

def _alert_hash(text: str) -> str:
    """Hash of spoken text — used to detect when conditions escalate (new text = re-alert)."""
    return hashlib.md5(text.encode()).hexdigest()[:12]


def _is_suppressed(alert_type: str, text: str, config: dict) -> bool:
    """
    Return True if this alert was spoken recently (within suppress window).
    Returns False (allow re-alert) if the text changed — conditions escalated.
    """
    window = config.get("tts_repeat_suppress_min", 30) * 60
    with _spoken_lock:
        entry = _spoken.get(alert_type)
    if not entry:
        return False
    # Re-alert if message text changed (conditions worsened or improved)
    if entry["text_hash"] != _alert_hash(text):
        return False
    return (time.time() - entry["time"]) < window


def _mark_spoken(alert_type: str, text: str) -> None:
    """Record that an alert was just spoken."""
    with _spoken_lock:
        _spoken[alert_type] = {"time": time.time(), "text_hash": _alert_hash(text)}


def _is_quiet_hours(config: dict) -> bool:
    """
    Return True if current time falls within configured quiet hours.
    Config keys: quiet_hours_start / quiet_hours_end  ("HH:MM" strings or None)
    """
    start_str = config.get("quiet_hours_start")
    end_str   = config.get("quiet_hours_end")
    if not start_str or not end_str:
        return False
    try:
        now   = datetime.now().time()
        start = dtime.fromisoformat(start_str)
        end   = dtime.fromisoformat(end_str)
        if start <= end:
            return start <= now <= end
        else:
            # Wraps midnight (e.g. 22:00 → 06:00)
            return now >= start or now <= end
    except Exception:
        return False


def _resolve_text(alert_type: str, config: dict) -> str:
    """
    Return the spoken text for an alert type in the driver's language.
    English → CB radio strings from claude/prompts.py
    Other   → t("tts.{alert_type}"), falls back to CB string
    """
    lang = config.get("language", "en")
    set_language(lang)

    if lang == "en":
        return cb_voice_alert(alert_type)

    # Try translated version first
    key      = f"tts.{alert_type}"
    translated = t(key)
    if translated != key:   # t() returns key itself when missing
        return translated

    # Fall back to English CB string
    return cb_voice_alert(alert_type)


def distance_to_severity(distance_mi: float) -> str:
    """
    Convert a distance-ahead (miles) to a TTS severity level.
    Used when speaking about route-ahead hazards from hazards.py / dot511.py.
    """
    if distance_mi <= DIST_CRITICAL_MI:
        return "CRITICAL"
    if distance_mi <= DIST_WARNING_MI:
        return "WARNING"
    return "INFO"


# ── Public API ────────────────────────────────────────────────────────────────

def speak(text: str, config: dict, bypass_quiet: bool = False) -> bool:
    """
    Low-level: speak arbitrary text through the platform engine.

    Checks:
      1. tts_enabled flag
      2. Quiet hours (unless bypass_quiet=True)

    Does NOT check repeat suppression — caller controls that.
    Returns True if speech dispatched, False if skipped/disabled.
    """
    if not config.get("tts_enabled", False):
        return False
    if not text or not text.strip():
        return False
    if not bypass_quiet and _is_quiet_hours(config):
        return False

    return _dispatch(text, config)


def speak_alert(alert_type: str, severity: str, config: dict,
                distance_mi: float = None, force: bool = False) -> bool:
    """
    Smart alert speech with all filters applied.

    Args:
        alert_type   : one of ALL_ALERT_TYPES (e.g. "black_ice")
        severity     : "CRITICAL" | "WARNING" | "INFO"
        config       : driver config dict
        distance_mi  : miles ahead (overrides severity via distance_to_severity)
        force        : bypass repeat suppression and quiet hours

    Routing:
        CRITICAL → speak immediately (bypasses quiet hours, bypasses queue)
        WARNING  → add to queue; speak immediately only if parked
        INFO     → add to queue only; never auto-fires
    """
    if not config.get("tts_enabled", False):
        return False

    # Distance can escalate or de-escalate severity
    if distance_mi is not None:
        severity = distance_to_severity(distance_mi)

    # INFO never auto-fires
    if severity == "INFO":
        _enqueue(alert_type, severity, config)
        return False

    text = _resolve_text(alert_type, config)
    if not text:
        return False

    # Repeat suppression (CRITICAL always fires the first time)
    if not force and _is_suppressed(alert_type, text, config):
        return False

    is_driving = config.get("is_driving", False)
    is_crit    = (severity == "CRITICAL")
    quiet      = _is_quiet_hours(config) and not (is_crit and CRITICAL_BYPASS_QUIET)

    if quiet:
        return False

    # Speed-aware: WARNING waits for a pause
    if severity == "WARNING" and is_driving and not force:
        _enqueue(alert_type, severity, config)
        return False

    # CRITICAL: speak now regardless of motion
    _mark_spoken(alert_type, text)
    return _dispatch(text, config)


def queue_warning(alert_type: str, config: dict) -> None:
    """
    Explicitly queue a WARNING alert to be spoken at next safe pause.
    Does nothing if TTS is disabled.
    """
    if config.get("tts_enabled", False):
        _enqueue(alert_type, "WARNING", config)


def _enqueue(alert_type: str, severity: str, config: dict) -> None:
    """Internal: add alert to queue if not already queued and not suppressed."""
    text = _resolve_text(alert_type, config)
    if not text:
        return
    if _is_suppressed(alert_type, text, config):
        return
    priority = _PRIORITY.get(severity, 99)
    entry    = (priority, alert_type, text, time.time())
    with _queue_lock:
        # Deduplicate: don't queue the same alert_type twice
        already = any(e[1] == alert_type for e in _queue)
        if not already:
            _queue.append(entry)
            _queue.sort(key=lambda e: e[0])   # keep sorted by priority


def flush_queue(config: dict, max_alerts: int = 3) -> int:
    """
    Speak all queued alerts in priority order (CRITICAL → WARNING → INFO).
    Call this when the vehicle parks or at a safe stopping point.

    Args:
        config     : driver config dict
        max_alerts : cap to avoid overwhelming the driver on resume

    Returns number of alerts spoken.
    """
    if not config.get("tts_enabled", False):
        return 0

    with _queue_lock:
        batch  = _queue[:max_alerts]
        del _queue[:max_alerts]

    spoken = 0
    for _, alert_type, text, _ in batch:
        if _is_suppressed(alert_type, text, config):
            continue
        if _dispatch(text, config):
            _mark_spoken(alert_type, text)
            spoken += 1
            time.sleep(0.3)   # brief gap between alerts

    return spoken


# speak_queued is an alias used by HOS guardian and parking module
speak_queued = flush_queue


def clear_suppression(alert_type: str = None) -> None:
    """
    Clear repeat-suppression cache so alerts can fire again.
    alert_type=None  → clear everything (e.g. after a major weather change).
    alert_type="black_ice" → clear only that type.
    """
    with _spoken_lock:
        if alert_type is None:
            _spoken.clear()
        else:
            _spoken.pop(alert_type, None)


def speak_all_active(alerts: list, config: dict) -> int:
    """
    Convenience: take a list of alert dicts from core/alerts.py and
    speak them in severity order, applying all smart filters.

    Returns number of alerts spoken or queued.
    """
    if not config.get("tts_enabled", False):
        return 0

    dispatched = 0
    for alert in alerts:
        alert_type = alert.get("type", "")
        severity   = alert.get("severity", "INFO")
        if speak_alert(alert_type, severity, config):
            dispatched += 1
    return dispatched


def queue_status(config: dict) -> dict:
    """
    Return diagnostic info about the TTS engine state.
    Useful for debug mode and the glance display.
    """
    with _queue_lock:
        q_snapshot = list(_queue)
    with _spoken_lock:
        s_snapshot = dict(_spoken)

    return {
        "tts_enabled":    config.get("tts_enabled", False),
        "platform":       _detect_platform_name(),
        "bt_connected":   _is_bt_connected(),
        "quiet_hours":    _is_quiet_hours(config),
        "queue_depth":    len(q_snapshot),
        "queued_types":   [e[1] for e in q_snapshot],
        "suppressed_cnt": len(s_snapshot),
        "language":       config.get("language", "en"),
    }


def _detect_platform_name() -> str:
    """Human-readable TTS platform name for diagnostics."""
    if _is_termux():
        return "termux-tts-speak"
    p = platform.system().lower()
    if p == "linux":
        return "pyttsx3 (Linux)"
    if p == "windows":
        return "Windows SAPI"
    if p == "darwin":
        return "AVSpeechSynthesizer / say"
    return "terminal fallback"


# ── "Hey Clean Shot" wake phrase stub (Phase 2) ───────────────────────────────

def set_wake_callback(callback) -> None:
    """
    Register a callback for "Hey Clean Shot" wake-word detection.
    callback(command_text: str) is called when a command is recognized.
    Full voice recognition is Phase 2 (core/voice.py).

    This stub stores the callback so callers can register early
    without breaking when voice.py is not yet active.
    """
    global _wake_callback
    _wake_callback = callback


def get_wake_phrase() -> str:
    """Return the configured wake phrase string."""
    return WAKE_PHRASE


def simulate_wake(command: str = "") -> bool:
    """
    Simulate a wake-word event for testing.
    Fires the registered callback if present.
    Returns True if a callback was registered.
    """
    if _wake_callback:
        _wake_callback(command)
        return True
    return False
