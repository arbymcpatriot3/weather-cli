#!/usr/bin/env python3
# platforms/android/tts_tones_android.py — Clean Shot: Alert Tones via sox (Android/Termux)
#
# Plays alert tones on Android using the sox 'play' command.
# Install: pkg install sox
#
# Tone design (mirrors Linux tone intent):
#   INFO      — 523 Hz  0.3s  (C5 — soft chime)
#   WARNING   — 440 Hz  0.5s  (A4 — ascending alert)
#   CRITICAL  — 880 Hz  0.8s  (A5 — urgent bong)
#   EMERGENCY — 880 Hz  rapid ×4  (cannot be missed)

import shutil
import subprocess

_TONES = {
    "info":      ("523", "0.3"),
    "warning":   ("440", "0.5"),
    "critical":  ("880", "0.8"),
    "emergency": ("880", "1.0"),
}


def sox_available() -> bool:
    """Return True if sox 'play' command is on PATH."""
    return bool(shutil.which("play"))


def play_tone_android(severity: str, config: dict = None) -> bool:
    """
    Play an alert tone on Android via sox.
    Returns True if played, False if sox is unavailable.
    Silently ignores all failures — tone is enhancement, not critical path.
    """
    if config is None:
        config = {}

    if not config.get("tts_tone_enabled", True):
        return False

    if not sox_available():
        return False

    sev = severity.lower()
    if sev not in _TONES:
        sev = "info"

    freq, dur = _TONES[sev]

    try:
        if sev == "emergency":
            for _ in range(4):
                subprocess.run(
                    ["play", "-n", "synth", dur, "sine", freq],
                    capture_output=True,
                    timeout=5,
                )
        else:
            subprocess.run(
                ["play", "-n", "synth", dur, "sine", freq],
                capture_output=True,
                timeout=5,
            )
        return True
    except Exception:
        return False
