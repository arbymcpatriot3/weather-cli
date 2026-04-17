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

import json
import os
import shutil
import subprocess
from pathlib import Path

# ── Piper voice catalog ───────────────────────────────────────────────────────
# HuggingFace URLs for voices that work well for trucking (US English, natural)
# Each entry: display_name, quality_stars, description
# Model files stored in ~/.local/share/piper/

PIPER_MODEL_DIR = Path.home() / ".local" / "share" / "piper"
PIPER_HF_BASE   = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"

PIPER_VOICES = {
    # name                    : (hf_path,                                  stars, description)
    "en_US-ryan-high"         : ("en/en_US/ryan/high",                     5, "Natural male — APPROVED ✓ clearest voice"),
    "en_US-ryan-medium"       : ("en/en_US/ryan/medium",                   5, "Natural male — clear & deep"),
    "en_US-lessac-medium"     : ("en/en_US/lessac/medium",                 5, "Natural male — backup"),
    "en_US-amy-medium"        : ("en/en_US/amy/medium",                    5, "Natural female"),
    "en_US-joe-medium"        : ("en/en_US/joe/medium",                    4, "Casual male"),
    "en_US-danny-low"         : ("en/en_US/danny/low",                     3, "Compact — fast download (~5MB)"),
    "en_US-kathleen-low"      : ("en/en_US/kathleen/low",                  3, "Compact female"),
}

# Short name aliases for `cleanshot settings voice ryan`
VOICE_ALIASES = {
    "ryan":    "en_US-ryan-high",
    "lessac":  "en_US-lessac-medium",
    "amy":     "en_US-amy-medium",
    "joe":     "en_US-joe-medium",
    "danny":   "en_US-danny-low",
    "kathleen": "en_US-kathleen-low",
}

DEFAULT_VOICE  = "en_US-ryan-high"
BACKUP_VOICE   = "en_US-lessac-medium"   # tried if default not installed


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

def _get_sample_rate(voice_name: str) -> int:
    """Read sample_rate from the voice's JSON config file. Falls back to 22050."""
    json_path = PIPER_MODEL_DIR / f"{voice_name}.onnx.json"
    try:
        with open(json_path) as f:
            data = json.load(f)
        return int(data["audio"]["sample_rate"])
    except Exception:
        return 22050


def _speak_piper(text: str, config: dict) -> bool:
    """
    Speak via piper-tts neural engine using the CLI subprocess approach.

    Proven working pipeline:
        echo "text" | piper --model model.onnx --output_raw |
        aplay -r 22050 -f S16_LE -t raw -q -

    Fires whenever the piper CLI + a voice model are installed.
    Does NOT use the Python PiperVoice API (wave header issue).
    """
    # Require: piper CLI in PATH
    piper_bin = shutil.which("piper")
    if not piper_bin:
        return False

    # Require: aplay for playback
    if not shutil.which("aplay"):
        return False

    voice_name = _active_voice(config)

    # Fall back through voice priority chain if configured voice not installed
    if not _voice_is_installed(voice_name):
        if _voice_is_installed(DEFAULT_VOICE):
            voice_name = DEFAULT_VOICE
        elif _voice_is_installed(BACKUP_VOICE):
            voice_name = BACKUP_VOICE
        else:
            return False

    model_path  = _get_voice_path(voice_name)
    sample_rate = _get_sample_rate(voice_name)
    debug       = os.environ.get("CLEANSHOT_DEBUG")

    try:
        # Step 1: piper — text → raw PCM via stdin/stdout
        piper_proc = subprocess.Popen(
            [piper_bin, "--model", str(model_path), "--output_raw", "--quiet"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Step 2: aplay — raw PCM → audio device
        aplay_proc = subprocess.Popen(
            ["aplay",
             "-r", str(sample_rate),
             "-f", "S16_LE",
             "-t", "raw",
             "-q", "-"],
            stdin=piper_proc.stdout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        # Close piper's stdout in THIS process so aplay gets EOF when piper exits
        piper_proc.stdout.close()

        # Feed text to piper
        _, piper_stderr = piper_proc.communicate(
            input=text.encode("utf-8"), timeout=30
        )
        aplay_proc.wait(timeout=30)

        if debug:
            print(f"[piper] rc={piper_proc.returncode} stderr={piper_stderr[:200]}")
            print(f"[aplay] rc={aplay_proc.returncode}")

        return aplay_proc.returncode == 0

    except subprocess.TimeoutExpired:
        if debug:
            print("[piper] timeout")
        try:
            piper_proc.kill()
            aplay_proc.kill()
        except Exception:
            pass
        return False
    except Exception as exc:
        if debug:
            print(f"[piper] exception: {exc}")
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


# ── Engine: espeak direct (subprocess) ───────────────────────────────────────
# Used on iOS iSH and any Linux where pyttsx3 fails to install.
# espeak-ng is preferred over legacy espeak.

def _speak_espeak_direct(text: str, rate: int = 130) -> bool:
    """
    Speak via espeak-ng or espeak subprocess directly — no pyttsx3 needed.
    Best voice on Alpine/iSH: en-us+m3 at rate 130.
    Falls back to espeak if espeak-ng not installed.
    Returns True if speech dispatched, False on failure.
    """
    for cmd in ("espeak-ng", "espeak"):
        if not shutil.which(cmd):
            continue
        try:
            subprocess.run(
                [cmd, "-v", "en+m3", "-s", str(rate), text],
                timeout=15,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            continue
    return False


# ── Engine: pyttsx3 ───────────────────────────────────────────────────────────

_degraded_warned = False   # show degraded-voice warning at most once per session


def _speak_pyttsx3(text: str, rate: int = 150, volume: float = 0.9) -> bool:
    """
    Speak via pyttsx3 (espeak backend) — FALLBACK ONLY.
    Voice en+m3 is more natural than the espeak default, but still robotic.
    Always shows a one-time "quality degraded" warning so the driver knows
    to run `cleanshot fix-voice`.
    """
    global _degraded_warned
    if not _degraded_warned:
        _degraded_warned = True
        print(
            "\n  ⚠️  Voice quality degraded — using espeak fallback"
            "\n     Run: cleanshot fix-voice    to restore natural voice\n"
        )
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

    # ── espeak direct (subprocess): works on iOS iSH and Alpine without pyttsx3
    if _speak_espeak_direct(text, rate):
        return True

    # ── pyttsx3/espeak: always the final fallback ──────────────────────────────
    return _speak_pyttsx3(text, rate, volume)


# ── Diagnostics ───────────────────────────────────────────────────────────────

def resolve_voice_alias(name: str) -> str:
    """
    Convert a short voice alias ('ryan') to a full voice name ('en_US-ryan-high').
    Returns the original name unchanged if not an alias.
    """
    return VOICE_ALIASES.get(name.lower(), name)


def get_engine_info(config: dict = None) -> dict:
    """
    Return info about the best available TTS engine.
    Used by cmd_test_tts() and doctor to show engine name and star rating.
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

    # Determine which piper voice is actually active
    if piper_available:
        active = None
        for candidate in (voice_name, DEFAULT_VOICE, BACKUP_VOICE):
            if _voice_is_installed(candidate):
                active = candidate
                break
        if active:
            stars = PIPER_VOICES.get(active, (None, 5, ""))[1]
            return {
                "engine":   "piper-tts (neural)",
                "voice":    active,
                "stars":    stars,
                "star_str": "⭐" * stars,
                "degraded": False,
            }

    if shutil.which("festival"):
        return {
            "engine":   "festival",
            "voice":    None,
            "stars":    3,
            "star_str": "⭐⭐⭐",
            "degraded": True,
        }

    # espeak direct (no pyttsx3 needed — works on Alpine/iSH)
    if shutil.which("espeak-ng") or shutil.which("espeak"):
        _is_ish = not shutil.which("apt-get") and not shutil.which("dnf")
        _note   = " (iOS iSH)" if _is_ish else ""
        return {
            "engine":   f"espeak en+m3{_note}",
            "voice":    None,
            "stars":    3,
            "star_str": "⭐⭐⭐",
            "degraded": True,
        }

    try:
        import pyttsx3  # noqa: F401
        return {
            "engine":   "pyttsx3 (espeak en+m3)",
            "voice":    None,
            "stars":    2,
            "star_str": "⭐⭐",
            "degraded": True,
        }
    except ImportError:
        pass

    return {
        "engine":   None,
        "voice":    None,
        "stars":    0,
        "star_str": "",
        "degraded": True,
    }


def fix_voice(show_progress: bool = True) -> bool:
    """
    Attempt to restore natural piper-tts voice quality.
    1. Install piper-tts via pip if missing
    2. Download ryan-high voice model
    3. Fall back to lessac-medium if ryan-high fails
    Returns True if piper voice is available after the call.
    """
    import subprocess as _sp

    def _msg(s: str):
        if show_progress:
            print(s)

    _msg("\n  🔊 FIXING VOICE QUALITY...\n")

    # ── Install piper-tts ─────────────────────────────────────────────────────
    piper_ok = False
    try:
        from piper import PiperVoice  # noqa: F401
        piper_ok = True
        _msg("  piper-tts          already installed ✅")
    except ImportError:
        _msg("  Installing piper-tts...            ", )
        for pip_args in (
            ["pip3", "install", "piper-tts", "--break-system-packages", "--quiet"],
            ["pip3", "install", "piper-tts", "--quiet"],
            ["pip",  "install", "piper-tts", "--break-system-packages", "--quiet"],
        ):
            try:
                _sp.run(pip_args, check=True, timeout=120,
                        stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
                from piper import PiperVoice  # noqa: F401
                piper_ok = True
                _msg("  piper-tts                          ✅")
                break
            except Exception:
                continue
        if not piper_ok:
            _msg("  piper-tts          install failed  ❌")
            _msg("     Fix: pip3 install piper-tts --break-system-packages")
            return False

    # ── Download voice model ──────────────────────────────────────────────────
    for voice_name in (DEFAULT_VOICE, BACKUP_VOICE):
        if _voice_is_installed(voice_name):
            _msg(f"  {voice_name}   already downloaded ✅")
            _msg(f"\n  Voice quality restored!")
            _msg(f"  Clean Shot is using: Piper TTS — {voice_name}")
            _msg(f"  Natural human voice ✅")
            _msg(f"\n  Test it: cleanshot test-tts\n")
            return True

        _msg(f"  Downloading {voice_name}...")
        if download_voice(voice_name, show_progress=show_progress):
            _msg(f"\n  Voice quality restored!")
            _msg(f"  Clean Shot is using: Piper TTS — {voice_name}")
            _msg(f"  Natural human voice ✅")
            _msg(f"\n  Test it: cleanshot test-tts\n")
            return True

    _msg("  Voice model download failed  ❌")
    _msg("     Fix: cleanshot voices download")
    return False
