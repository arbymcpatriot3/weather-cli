#!/usr/bin/env python3
# tests/test_tts.py — Clean Shot: TTS module tests
# Tests the dispatch logic and CB voice string lookup — no actual audio output.

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claude.prompts import cb_voice_alert


def test_cb_voice_alert_known():
    text = cb_voice_alert("black_ice")
    assert text, "Expected non-empty string for black_ice"
    assert "buddy" in text.lower() or "back" in text.lower(), f"Got: {text}"
    print(f"✓ cb_voice_alert black_ice: '{text}'")


def test_cb_voice_alert_unknown():
    text = cb_voice_alert("nonexistent_type")
    assert text == "", f"Expected empty string, got: '{text}'"
    print("✓ cb_voice_alert unknown type returns empty string")


def test_tts_disabled_by_default():
    from core.tts import speak
    result = speak("test", {"tts_enabled": False})
    assert result is False
    print("✓ TTS disabled when tts_enabled=False")


if __name__ == "__main__":
    test_cb_voice_alert_known()
    test_cb_voice_alert_unknown()
    test_tts_disabled_by_default()
    print("All TTS tests passed.")
