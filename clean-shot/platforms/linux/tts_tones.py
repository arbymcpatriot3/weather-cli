#!/usr/bin/env python3
# platforms/linux/tts_tones.py — Clean Shot: Alert Tone Generator
#
# Generates distinctive WAV tones for each severity level.
# Pure Python — no numpy, no downloads, no internet.
# Generated once on first use, cached in ~/.local/share/cleanshot/tones/
#
# Tone design:
#   INFO      — soft ascending chime    C5→E5       0.3s  "ding-ding"
#   WARNING   — medium ascending alert  A4→C5→E5    0.5s  "ding-ding-ding"
#   CRITICAL  — urgent descending       A5→F5→D5    0.8s  "BONG-BONG-BONG"
#   EMERGENCY — rapid high pulse        A5 x8       1.0s  cannot be missed

import io
import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

TONE_DIR    = Path.home() / ".local" / "share" / "cleanshot" / "tones"
SAMPLE_RATE = 22050

TONE_FILES = {
    "INFO":      "info.wav",
    "WARNING":   "warning.wav",
    "CRITICAL":  "critical.wav",
    "EMERGENCY": "emergency.wav",
}


# ── Primitive audio building blocks ──────────────────────────────────────────

def _sine_segment(freq: float, duration: float, volume: float) -> bytes:
    """
    Generate a mono 16-bit PCM sine wave segment with linear fade in/out.
    Returns raw PCM bytes (not a WAV container).
    """
    frames     = int(duration * SAMPLE_RATE)
    fade_f     = max(1, int(frames * 0.15))   # 15% of segment
    audio      = []
    for i in range(frames):
        env = min(i, fade_f, frames - i) / fade_f
        env = min(env, 1.0)
        val = int(volume * env * 32767 *
                  math.sin(2.0 * math.pi * freq * i / SAMPLE_RATE))
        val = max(-32767, min(32767, val))
        audio.append(struct.pack('<h', val))
    return b''.join(audio)


def _silence(duration: float) -> bytes:
    """Return PCM silence of given duration."""
    return b'\x00\x00' * int(duration * SAMPLE_RATE)


def _to_wav(pcm: bytes) -> bytes:
    """Wrap raw mono 16-bit PCM in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)
    return buf.getvalue()


# ── Tone composers ────────────────────────────────────────────────────────────

def _make_info_tone(volume: float) -> bytes:
    """
    INFO — soft ascending chime: C5 (523 Hz) → E5 (659 Hz)
    Duration ≈ 0.30 s   "ding-ding"
    """
    gap  = _silence(0.04)
    seg1 = _sine_segment(523.25, 0.13, volume * 0.75)   # C5 — softer
    seg2 = _sine_segment(659.25, 0.13, volume * 0.75)   # E5
    return _to_wav(seg1 + gap + seg2)


def _make_warning_tone(volume: float) -> bytes:
    """
    WARNING — ascending alert: A4 (440 Hz) → C5 (523 Hz) → E5 (659 Hz)
    Duration ≈ 0.50 s   "ding-ding-ding"
    """
    gap  = _silence(0.03)
    seg1 = _sine_segment(440.00, 0.14, volume)          # A4
    seg2 = _sine_segment(523.25, 0.14, volume)          # C5
    seg3 = _sine_segment(659.25, 0.14, volume)          # E5
    return _to_wav(seg1 + gap + seg2 + gap + seg3)


def _make_critical_tone(volume: float) -> bytes:
    """
    CRITICAL — urgent descending: A5 (880 Hz) → F5 (698 Hz) → D5 (587 Hz)
    Duration ≈ 0.80 s   "BONG-BONG-BONG"  Descending = danger.
    """
    gap  = _silence(0.04)
    seg1 = _sine_segment(880.00, 0.24, volume)          # A5
    seg2 = _sine_segment(698.46, 0.24, volume)          # F5
    seg3 = _sine_segment(587.33, 0.24, volume)          # D5
    return _to_wav(seg1 + gap + seg2 + gap + seg3)


def _make_emergency_tone(volume: float) -> bytes:
    """
    EMERGENCY — rapid urgent pulse: A5 (880 Hz) x 8 rapid bursts
    Duration ≈ 1.00 s   Cannot be missed.
    """
    gap   = _silence(0.025)
    pulse = _sine_segment(880.00, 0.085, volume)        # short burst
    pcm   = b''
    for i in range(8):
        pcm += pulse + gap
    return _to_wav(pcm)


# ── Tone file management ──────────────────────────────────────────────────────

def _tone_path(severity: str) -> Path:
    filename = TONE_FILES.get(severity.upper(), "info.wav")
    return TONE_DIR / filename


def ensure_tones(volume: float = 0.8, force: bool = False) -> bool:
    """
    Generate all 4 tone WAV files if missing (or force=True).
    Returns True if all tones exist after the call.
    No network, no downloads — all generated locally.
    """
    TONE_DIR.mkdir(parents=True, exist_ok=True)

    makers = {
        "INFO":      _make_info_tone,
        "WARNING":   _make_warning_tone,
        "CRITICAL":  _make_critical_tone,
        "EMERGENCY": _make_emergency_tone,
    }

    for severity, make_fn in makers.items():
        path = _tone_path(severity)
        if force or not path.exists():
            try:
                wav_bytes = make_fn(volume)
                path.write_bytes(wav_bytes)
            except Exception:
                return False

    return all(_tone_path(s).exists() for s in makers)


def tones_exist() -> bool:
    """Return True if all 4 tone files are present."""
    return all(_tone_path(s).exists() for s in TONE_FILES)


# ── Tone playback ─────────────────────────────────────────────────────────────

def play_tone(severity: str, config: dict = None) -> bool:
    """
    Play the alert tone for the given severity level.
    Generates tones if missing. Returns True if played.

    config keys read:
        tts_tone_enabled : bool  (default True)
        tts_tone_volume  : float (default 0.8, range 0.0–1.0)
    """
    if config is None:
        config = {}

    if not config.get("tts_tone_enabled", True):
        return False

    sev = severity.upper()
    if sev not in TONE_FILES:
        sev = "INFO"

    volume = float(config.get("tts_tone_volume", 0.8))
    volume = max(0.0, min(1.0, volume))

    # Generate tones if any are missing
    if not _tone_path(sev).exists():
        ensure_tones(volume)

    path = _tone_path(sev)
    if not path.exists():
        return False

    return _play_wav(path)


def _play_wav(path: Path) -> bool:
    """Play a WAV file via aplay (or ffplay fallback). Non-blocking on failure."""
    if shutil.which("aplay"):
        try:
            result = subprocess.run(
                ["aplay", "-q", str(path)],
                timeout=5,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return result.returncode == 0
        except Exception:
            pass

    if shutil.which("ffplay"):
        try:
            result = subprocess.run(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)],
                timeout=5,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return result.returncode == 0
        except Exception:
            pass

    # python wave + write to /dev/audio as last resort
    try:
        import ossaudiodev  # Linux OSS — rarely available but worth trying
        dsp = ossaudiodev.open('w')
        dsp.setparameters(ossaudiodev.AFMT_S16_LE, 1, SAMPLE_RATE)
        dsp.write(path.read_bytes()[44:])   # skip WAV header
        dsp.close()
        return True
    except Exception:
        pass

    return False


# ── In-process playback (no aplay — for CI/testing) ──────────────────────────

def play_tone_bytes(severity: str, config: dict = None) -> bytes:
    """
    Return the raw WAV bytes for a severity tone without playing.
    Used for testing and for piping to external players.
    """
    if config is None:
        config = {}
    volume = float(config.get("tts_tone_volume", 0.8))
    volume = max(0.0, min(1.0, volume))

    makers = {
        "INFO":      _make_info_tone,
        "WARNING":   _make_warning_tone,
        "CRITICAL":  _make_critical_tone,
        "EMERGENCY": _make_emergency_tone,
    }
    sev = severity.upper() if severity.upper() in makers else "INFO"
    return makers[sev](volume)
