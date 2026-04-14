#!/usr/bin/env python3
# platforms/linux/tts_linux.py — Clean Shot: Linux TTS
#
# Quality cascade (best available wins):
#   piper    → neural TTS (most natural — fires whenever model is installed)
#   festival → more natural than espeak
#   pyttsx3  → espeak with en+m3 voice, 150 WPM (always available fallback)
#
# Config keys read:
#   tts_voice_quality : "standard" | "enhanced" | "premium"  (default: enhanced)
#   tts_voice_name    : piper voice name                      (default: en_US-lessac-medium)
#   tts_rate          : words per minute                      (default: 150)
#   tts_volume        : 0.0 – 1.0                            (default: 0.9)

import io
import os
import shutil
import subprocess
import wave
from pathlib import Path

# ── Piper voice catalog ───────────────────────────────────────────────────────
# HuggingFace URLs for voices that work well for trucking (US English, natural)
# Each entry: display_name, quality_stars, description
# Model files stored in ~/.local/share/piper/

PIPER_MODEL_DIR = Path.home() / ".local" / "share" / "piper"
PIPER_HF_BASE   = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"

PIPER_VOICES = {
    # name                    : (hf_path,                                  stars, description)
    "en_US-lessac-medium"     : ("en/en_US/lessac/medium",                 5, "Natural male — recommended"),
    "en_US-ryan-medium"       : ("en/en_US/ryan/medium",                   5, "Natural male — clear & deep"),
    "en_US-amy-medium"        : ("en/en_US/amy/medium",                    5, "Natural female"),
    "en_US-joe-medium"        : ("en/en_US/joe/medium",                    4, "Casual male"),
    "en_US-danny-low"         : ("en/en_US/danny/low",                     3, "Compact — fast download (~5MB)"),
    "en_US-kathleen-low"      : ("en/en_US/kathleen/low",                  3, "Compact female"),
}

DEFAULT_VOICE = "en_US-lessac-medium"


# ── Voice path helpers ────────────────────────────────────────────────────────

def _get_voice_path(voice_name: str) -> Path:
    """Return the local .onnx model path for a given voice name."""
    return PIPER_MODEL_DIR / f"{voice_name}.onnx"


def _voice_is_installed(voice_name: str) -> bool:
    """Return True if the voice model file exists locally."""
    return _get_voice_path(voice_name).exists()


def _active_voice(config: dict) -> str:
    """Return the configured voice name, falling back to default."""
    return config.get("tts_voice_name", DEFAULT_VOICE)


# ── Voice download ────────────────────────────────────────────────────────────

def download_voice(voice_name: str, show_progress: bool = True) -> bool:
    """
    Download a piper voice model + JSON config to ~/.local/share/piper/.
    Returns True on success, False on failure.
    Requires: pip install requests
    """
    if voice_name not in PIPER_VOICES:
        print(f"  Unknown voice: {voice_name}")
        print(f"  Run: cleanshot voices  to see available voices")
        return False

    PIPER_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    hf_path = PIPER_VOICES[voice_name][0]
    base_url = f"{PIPER_HF_BASE}/{hf_path}/{voice_name}"

    for ext in (".onnx", ".onnx.json"):
        url      = base_url + ext
        out_path = PIPER_MODEL_DIR / f"{voice_name}{ext}"

        if out_path.exists():
            continue

        if show_progress:
            label = "model" if ext == ".onnx" else "config"
            print(f"  Downloading {voice_name} ({label})...")

        try:
            import urllib.request
            urllib.request.urlretrieve(url, str(out_path))
        except Exception as e:
            if show_progress:
                print(f"  ❌ Download failed: {e}")
                print(f"     Check your connection and try again.")
            # Clean up partial download
            if out_path.exists():
                out_path.unlink()
            return False

    if show_progress:
        print(f"  ✅ {voice_name} installed")
    return True


# ── Voice listing ─────────────────────────────────────────────────────────────

def list_voices(config: dict = None) -> None:
    """Print the voice catalog with download status."""
    if config is None:
        config = {}
    active = _active_voice(config)

    print()
    print("  Piper Voices — Clean Shot")
    print("  " + "─" * 37)
    print()
    for name, (_, stars, desc) in PIPER_VOICES.items():
        installed = _voice_is_installed(name)
        star_str  = "⭐" * stars
        status    = "✅" if installed else "  "
        marker    = " ◀ active" if (name == active and installed) else ""
        print(f"  {status} {star_str}  {name}")
        print(f"       {desc}{marker}")
        if not installed:
            print(f"       cleanshot voices download {name}")
        print()

    print("  To change voice:")
    print("    cleanshot settings voice <name>")
    print()


# ── Engine: piper ─────────────────────────────────────────────────────────────

def _play_audio(wav_bytes: bytes) -> bool:
    """Play WAV bytes via aplay (or ffplay fallback). Returns True on success."""
    if shutil.which("aplay"):
        try:
            result = subprocess.run(
                ["aplay", "-q", "-"],
                input=wav_bytes,
                timeout=30,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return result.returncode == 0
        except Exception:
            pass

    if shutil.which("ffplay"):
        try:
            result = subprocess.run(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-"],
                input=wav_bytes,
                timeout=30,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return result.returncode == 0
        except Exception:
            pass

    return False


def _speak_piper(text: str, config: dict) -> bool:
    """
    Speak via piper-tts neural engine.
    Fires whenever a voice model is installed — regardless of quality setting.
    Requires: pip3 install piper-tts --break-system-packages
              cleanshot voices download  (downloads default voice model)
    """
    try:
        from piper import PiperVoice  # noqa: F401 — check import first
    except ImportError:
        return False

    voice_name = _active_voice(config)

    # Fall back to default if configured voice isn't installed
    if not _voice_is_installed(voice_name):
        if voice_name != DEFAULT_VOICE and _voice_is_installed(DEFAULT_VOICE):
            voice_name = DEFAULT_VOICE
        else:
            return False

    model_path = _get_voice_path(voice_name)

    try:
        from piper import PiperVoice
        voice = PiperVoice.load(str(model_path))

        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            voice.synthesize(text, wav_file)
        wav_bytes = wav_io.getvalue()

        return _play_audio(wav_bytes)
    except Exception:
        return False


# ── Engine: festival ──────────────────────────────────────────────────────────

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


# ── Engine: pyttsx3 ───────────────────────────────────────────────────────────

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


# ── Public dispatch ───────────────────────────────────────────────────────────

def speak_linux(text: str, config: dict = None) -> bool:
    """
    Speak text on Linux using the best available TTS engine.
    config is optional — all keys fall back to sensible defaults.

    Cascade order (first success wins):
      1. piper-tts    — neural, most natural (fires if model installed)
      2. festival     — more natural than espeak (if installed)
      3. pyttsx3      — espeak en+m3 fallback (always available)

    Returns True if speech was dispatched, False on total failure.
    """
    if config is None:
        config = {}

    rate   = int(config.get("tts_rate",   150))
    volume = float(config.get("tts_volume", 0.9))

    # ── Piper: fires whenever model is installed ───────────────────────────────
    if _speak_piper(text, config):
        return True

    # ── Festival: quality setting must be enhanced or premium ─────────────────
    quality = config.get("tts_voice_quality", "enhanced")
    if quality in ("premium", "enhanced"):
        if _speak_festival(text):
            return True

    # ── pyttsx3/espeak: always the final fallback ──────────────────────────────
    return _speak_pyttsx3(text, rate, volume)


# ── Diagnostics ───────────────────────────────────────────────────────────────

def get_engine_info(config: dict = None) -> dict:
    """
    Return info about the best available TTS engine.
    Used by cmd_test_tts() to show engine name and star rating.
    """
    if config is None:
        config = {}

    voice_name = _active_voice(config)

    # Check piper first
    try:
        from piper import PiperVoice  # noqa: F401
        piper_available = True
    except ImportError:
        piper_available = False

    piper_installed = _voice_is_installed(voice_name) or _voice_is_installed(DEFAULT_VOICE)

    if piper_available and piper_installed:
        active = voice_name if _voice_is_installed(voice_name) else DEFAULT_VOICE
        stars  = PIPER_VOICES.get(active, (None, 5, ""))[1]
        return {
            "engine":     "piper-tts (neural)",
            "voice":      active,
            "stars":      stars,
            "star_str":   "⭐" * stars,
        }

    if shutil.which("festival"):
        return {
            "engine":   "festival",
            "voice":    None,
            "stars":    3,
            "star_str": "⭐⭐⭐",
        }

    try:
        import pyttsx3  # noqa: F401
        return {
            "engine":   "pyttsx3 (espeak en+m3)",
            "voice":    None,
            "stars":    2,
            "star_str": "⭐⭐",
        }
    except ImportError:
        pass

    return {
        "engine":   None,
        "voice":    None,
        "stars":    0,
        "star_str": "",
    }
