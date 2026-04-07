#!/usr/bin/env python3
# core/voice.py — Clean Shot: "Hey Clean Shot" wake-word + voice commands
# Tier: Solo Pro+
# Platform: Linux (pvporcupine or vosk), iOS (SFSpeechRecognizer bridge)
#
# Design principles:
#   - Wake word detection is OFFLINE only (battery + privacy)
#   - Command recognition uses local vosk model (< 50 MB)
#   - No audio is ever uploaded
#   - Disabled by default — driver opts in via settings
#
# Supported commands (planned):
#   "Hey Clean Shot, what's the weather?"
#   "Hey Clean Shot, any hazards ahead?"
#   "Hey Clean Shot, find me parking"
#   "Hey Clean Shot, I'm pulling over" (triggers HOS stop)
#
# TODO: implement in module sprint


def is_available() -> bool:
    """Return True if voice input is available on this platform. Stub."""
    return False


def start_listening(config: dict, callback) -> bool:
    """
    Start background wake-word detection.
    callback(command_text) is called when a command is recognized.
    Returns True if listener started. Stub.
    """
    # TODO: platform check, load wake-word model, start thread
    return False


def stop_listening() -> None:
    """Stop background wake-word detection. Stub."""
    pass


def process_command(text: str, config: dict) -> str:
    """
    Parse a recognized voice command string and return the action key.
    Returns action string or 'unknown'. Stub.
    """
    text = text.lower()
    if "weather" in text:
        return "weather"
    if "hazard" in text or "ahead" in text:
        return "hazards"
    if "parking" in text:
        return "parking"
    if "pulling over" in text or "stop" in text:
        return "hos_stop"
    return "unknown"
