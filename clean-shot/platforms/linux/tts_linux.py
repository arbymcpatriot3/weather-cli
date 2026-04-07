#!/usr/bin/env python3
# platforms/linux/tts_linux.py — Clean Shot: Linux TTS via pyttsx3
# Fully offline. No network call. Install: pip install pyttsx3
# TODO: implement in module sprint

def speak_linux(text: str) -> bool:
    """Speak text using pyttsx3 (offline). Returns True on success."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)   # words per minute — comfortable for alerts
        engine.setProperty("volume", 0.9)
        engine.say(text)
        engine.runAndWait()
        return True
    except Exception:
        return False
