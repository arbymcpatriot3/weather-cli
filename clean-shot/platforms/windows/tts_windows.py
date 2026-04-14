#!/usr/bin/env python3
# platforms/windows/tts_windows.py — Clean Shot: Windows SAPI TTS
# Uses built-in Windows Speech API — no install required.
# Config keys read:
#   tts_rate   : words per minute (default 150 → SAPI rate -1)
#   tts_volume : 0.0 – 1.0       (default 0.9 → SAPI volume 90)

import subprocess


def speak_windows(text: str, config: dict = None) -> bool:
    """Speak text using Windows SAPI. Returns True on success."""
    if config is None:
        config = {}

    rate   = int(config.get("tts_rate",   150))
    volume = float(config.get("tts_volume", 0.9))

    # SAPI rate: -10 (slowest) to 10 (fastest), 0 ≈ 180 WPM
    # 150 WPM maps to approximately -1
    sapi_rate = max(-5, min(5, round((rate - 180) / 20)))
    sapi_vol  = int(max(0.0, min(1.0, volume)) * 100)

    # Escape quotes in text for safety
    safe_text = text.replace('"', "'").replace("'", "\\'")

    try:
        import win32com.client
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Rate   = sapi_rate
        speaker.Volume = sapi_vol
        speaker.Speak(text)
        return True
    except Exception:
        pass

    try:
        cmd = (
            f"Add-Type -AssemblyName System.Speech; "
            f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Rate = {sapi_rate}; "
            f"$s.Volume = {sapi_vol}; "
            f"$s.Speak('{safe_text}')"
        )
        subprocess.run(
            ["powershell", "-Command", cmd],
            timeout=15, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False
