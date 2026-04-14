#!/usr/bin/env python3
# platforms/linux/tts_linux.py — Clean Shot: Linux TTS
#
# Quality cascade (best available wins):
#   premium  → piper-tts (neural, Phase 2 stub)
#   enhanced → festival  (much more natural than espeak)
#   standard → pyttsx3   (espeak with en+m3 voice, 150 WPM)
#
# Config keys read:
#   tts_voice_quality : "standard" | "enhanced" | "premium"  (default: enhanced)
#   tts_rate          : words per minute                      (default: 150)
#   tts_volume        : 0.0 – 1.0                            (default: 0.9)

import shutil
import subprocess


def speak_linux(text: str, config: dict = None) -> bool:
    """
    Speak text on Linux using the best available TTS engine.
    config is optional — all keys fall back to sensible defaults.
    Returns True if speech was dispatched, False on total failure.
    """
    if config is None:
        config = {}

    quality = config.get("tts_voice_quality", "enhanced")
    rate    = int(config.get("tts_rate",   150))
    volume  = float(config.get("tts_volume", 0.9))

    # ── Premium: piper-tts neural engine (Phase 2 — needs model file) ─────────
    if quality == "premium":
        if _speak_piper(text, config):
            return True
        # Fall through to enhanced

    # ── Enhanced: festival (significantly more natural than espeak) ────────────
    if quality in ("premium", "enhanced"):
        if _speak_festival(text):
            return True
        # Fall through to standard

    # ── Standard: pyttsx3 / espeak with tuned voice + rate ────────────────────
    return _speak_pyttsx3(text, rate, volume)


# ── Engine implementations ────────────────────────────────────────────────────

def _speak_festival(text: str) -> bool:
    """
    Speak via festival TTS — much more natural than espeak.
    Requires: sudo apt-get install -y festival festvox-us-slt-hts
    """
    if not shutil.which("festival"):
        return False
    try:
        proc = subprocess.Popen(
            ["festival", "--tts"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        proc.communicate(input=text.encode(), timeout=20)
        return proc.returncode == 0
    except Exception:
        return False


def _speak_pyttsx3(text: str, rate: int = 150, volume: float = 0.9) -> bool:
    """
    Speak via pyttsx3 (espeak backend) with tuned settings.
    Voice en+m3 sounds noticeably more natural than espeak default.
    Rate 150 WPM feels unhurried vs the 200 WPM default.
    """
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate",   rate)
        engine.setProperty("volume", volume)
        # en+m3 is a male variant with more natural cadence than default 'en'
        # espeak-ng accepts this directly even if not listed in getProperty("voices")
        try:
            engine.setProperty("voice", "en+m3")
        except Exception:
            pass
        engine.say(text)
        engine.runAndWait()
        engine.stop()
        return True
    except Exception:
        return False


def _speak_piper(text: str, config: dict) -> bool:
    """
    Speak via piper-tts neural engine (Phase 2).
    Requires: pip3 install piper-tts --break-system-packages
    AND a downloaded voice model file.
    Full model management will be in core/tts_models.py (Phase 2).
    """
    try:
        import piper  # noqa: F401
        # Model path management is Phase 2
        return False
    except ImportError:
        return False
