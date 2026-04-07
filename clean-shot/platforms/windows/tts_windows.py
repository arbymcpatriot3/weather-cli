#!/usr/bin/env python3
# platforms/windows/tts_windows.py — Clean Shot: Windows SAPI TTS
# Uses built-in Windows Speech API — no install required.
# TODO: implement in module sprint

def speak_windows(text: str) -> bool:
    """Speak text using Windows SAPI. Returns True on success."""
    try:
        import win32com.client
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Speak(text)
        return True
    except Exception:
        pass
    try:
        # Fallback: PowerShell Add-Type SpeechSynthesizer
        import subprocess
        cmd = (
            f'Add-Type -AssemblyName System.Speech; '
            f'$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
            f'$s.Speak("{text}")'
        )
        subprocess.run(["powershell", "-Command", cmd], timeout=10, check=True)
        return True
    except Exception:
        return False
