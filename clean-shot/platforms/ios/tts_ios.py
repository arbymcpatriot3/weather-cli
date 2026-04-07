#!/usr/bin/env python3
# platforms/ios/tts_ios.py — Clean Shot: iOS AVSpeechSynthesizer bridge
# Called from core/tts.py when platform == "ios" (Pythonista/Pyto).
# Uses objc_util (Pythonista) or ctypes bridge to call AVSpeechSynthesizer.
# TODO: implement in module sprint

def speak_ios(text: str) -> bool:
    """Speak text via AVSpeechSynthesizer. Returns True on success."""
    try:
        # Pythonista path
        from objc_util import ObjCClass
        AVSpeechSynthesizer = ObjCClass("AVSpeechSynthesizer")
        AVSpeechUtterance   = ObjCClass("AVSpeechUtterance")
        synth     = AVSpeechSynthesizer.new()
        utterance = AVSpeechUtterance.speechUtteranceWithString_(text)
        utterance.rate = 0.5
        synth.speakUtterance_(utterance)
        return True
    except Exception:
        pass

    try:
        # Pyto path — uses speech module if available
        import speech
        speech.say(text, "en-US")
        return True
    except Exception:
        return False
