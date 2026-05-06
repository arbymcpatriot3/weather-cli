#!/usr/bin/env python3
# platforms/windows/tts_windows.py — Clean Shot: Windows SAPI TTS
# Uses built-in Windows Speech API — no install required.
#
# Voice quality standard:
#   Preferred voices (natural): David, Mark
#   Avoid: Microsoft Sam (robotic), Zira (older)
#   Config key: tts_windows_voice (default "David")
#
# Config keys read:
#   tts_rate          : words per minute (default 150 → SAPI rate -1)
#   tts_volume        : 0.0 – 1.0       (default 0.9 → SAPI volume 90)
#   tts_windows_voice : preferred SAPI voice name fragment (default "David")

import subprocess

# Preferred SAPI voices in priority order (natural quality, never robotic)
_PREFERRED_VOICES = ["David", "Mark", "Zira"]


def _select_voice(voices, preferred: str) -> object:
    """
    Return the best available SAPI voice object.
    Tries preferred name first, then falls back through _PREFERRED_VOICES,
    then returns first available voice (never None if voices exist).
    """
    preferred_lower = preferred.lower()

    # Try configured preference first
    for v in voices:
        if preferred_lower in v.GetDescription().lower():
            return v

    # Try other natural-sounding voices
    for name in _PREFERRED_VOICES:
        for v in voices:
            if name.lower() in v.GetDescription().lower():
                return v

    # Avoid "Sam" (Microsoft Sam is very robotic)
    non_sam = [v for v in voices if "sam" not in v.GetDescription().lower()]
    if non_sam:
        return non_sam[0]

    # Last resort: whatever is available
    return voices[0] if voices else None


def speak_windows(text: str, config: dict = None) -> bool:
    """Speak text using Windows SAPI with natural voice. Returns True on success."""
    if config is None:
        config = {}

    rate      = int(config.get("tts_rate",           150))
    volume    = float(config.get("tts_volume",         0.9))
    preferred = config.get("tts_windows_voice",       "David")

    # SAPI rate: -10 (slowest) to 10 (fastest), 0 ≈ 180 WPM
    sapi_rate = max(-5, min(5, round((rate - 180) / 20)))
    sapi_vol  = int(max(0.0, min(1.0, volume)) * 100)

    # Escape chars special in PowerShell double-quoted strings
    safe_text = (text
                 .replace('`', '``')   # backtick first — PS escape char
                 .replace('"', '`"')   # double-quote
                 .replace('$', '`$'))  # dollar sign (variable sigil)

    # ── win32com path (most reliable) ─────────────────────────────────────────
    try:
        import win32com.client
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Rate   = sapi_rate
        speaker.Volume = sapi_vol

        voices = speaker.GetVoices()
        best   = _select_voice(list(voices), preferred)
        if best:
            speaker.Voice = best

        speaker.Speak(text)
        return True
    except Exception:
        pass

    # ── PowerShell fallback ───────────────────────────────────────────────────
    try:
        # Select natural voice in PowerShell
        voice_sel = (
            f"$voices = $s.GetInstalledVoices() | ForEach-Object {{$_.VoiceInfo}}; "
            f"$v = $voices | Where-Object {{$_.Name -like '*{preferred}*'}} | "
            f"Select-Object -First 1; "
            f"if ($v) {{$s.SelectVoice($v.Name)}}"
        )
        cmd = (
            f"Add-Type -AssemblyName System.Speech; "
            f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Rate = {sapi_rate}; "
            f"$s.Volume = {sapi_vol}; "
            f"{voice_sel}; "
            f'$s.Speak("{safe_text}")'
        )
        import base64
        cmd_b64 = base64.b64encode(cmd.encode("utf-16-le")).decode("ascii")
        subprocess.run(
            ["powershell", "-EncodedCommand", cmd_b64],
            timeout=15, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False
