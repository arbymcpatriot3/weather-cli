#!/usr/bin/env python3
# platforms/ios/tts_ios.py — Clean Shot: iOS AVSpeechSynthesizer bridge
# Called from core/tts.py when platform == "ios" (Pythonista/Pyto).
# Uses objc_util (Pythonista) or ctypes bridge to call AVSpeechSynthesizer.
# TODO: implement in module sprint

def speak_ios(text: str, config: dict = None) -> bool:
    """
    Speak text via AVSpeechSynthesizer with natural voice.
    Prefers Samantha (natural female) or Daniel (UK male) over default.
    Returns True on success.
    """
    if config is None:
        config = {}

    rate = float(config.get("tts_rate", 150)) / 300.0  # normalize to 0.0–1.0
    rate = max(0.2, min(0.8, rate))                     # AVSpeech range

    try:
        # Pythonista path
        from objc_util import ObjCClass
        AVSpeechSynthesizer = ObjCClass("AVSpeechSynthesizer")
        AVSpeechUtterance   = ObjCClass("AVSpeechUtterance")
        AVSpeechSynthesisVoice = ObjCClass("AVSpeechSynthesisVoice")

        synth     = AVSpeechSynthesizer.new()
        utterance = AVSpeechUtterance.speechUtteranceWithString_(text)
        utterance.rate = rate

        # Prefer natural voices: Samantha (en-US female) or Daniel (en-GB male)
        for lang_code in ("en-US", "en-GB"):
            try:
                voice = AVSpeechSynthesisVoice.voiceWithLanguage_(lang_code)
                if voice:
                    utterance.voice = voice
                    break
            except Exception:
                pass

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
