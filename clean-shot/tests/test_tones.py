#!/usr/bin/env python3
# tests/test_tones.py — Clean Shot: Alert tone + repeat + voice selection tests
# No audio output — all tests are logic-only.
# Tones are generated in memory (play_tone is never called).
#
# Compatible with both direct execution and pytest.

import io
import os
import sys
import tempfile
import wave
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from platforms.linux.tts_tones import (
    _sine_segment, _silence, _to_wav,
    _make_info_tone, _make_warning_tone, _make_critical_tone, _make_emergency_tone,
    play_tone_bytes, SAMPLE_RATE, TONE_FILES, TONE_DIR,
    ensure_tones, tones_exist, _tone_path,
)
from platforms.linux.tts_linux import (
    PIPER_VOICES, VOICE_ALIASES, DEFAULT_VOICE, BACKUP_VOICE,
    _active_voice, _get_voice_path, resolve_voice_alias,
    get_engine_info,
)
from core.tts import (
    _store_message, get_last_messages,
    _last_messages, _last_msg_lock,
    _PRIORITY,
)

# ─────────────────────────────────────────────────────────────────────────────

_passed = 0
_failed = 0


def _ok(name: str):
    global _passed
    _passed += 1
    print(f"✓ {name}")


def _fail(name: str, reason: str):
    global _failed
    _failed += 1
    print(f"✗ {name}: {reason}")


def _check(name: str, condition: bool, reason: str = ""):
    if condition:
        _ok(name)
    else:
        _fail(name, reason or "condition was False")


def _wav_duration(wav_bytes: bytes) -> float:
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, 'rb') as wf:
        return wf.getnframes() / wf.getframerate()


# ─────────────────────────────────────────────────────────────────────────────
# Test functions (callable by pytest as well as directly)
# ─────────────────────────────────────────────────────────────────────────────

def test_sine_segment():
    seg = _sine_segment(440.0, 0.1, 0.8)
    _check("sine_segment: correct byte length",
           len(seg) == int(0.1 * SAMPLE_RATE) * 2,
           f"got {len(seg)}, expected {int(0.1*SAMPLE_RATE)*2}")
    _check("sine_segment: returns bytes",  isinstance(seg, bytes))
    _check("sine_segment: non-zero content", any(b != 0 for b in seg))
    assert len(seg) == int(0.1 * SAMPLE_RATE) * 2


def test_silence():
    sil = _silence(0.1)
    _check("silence: correct length",
           len(sil) == int(0.1 * SAMPLE_RATE) * 2)
    _check("silence: all zeros", all(b == 0 for b in sil))
    assert all(b == 0 for b in sil)


def test_wav_container():
    pcm = _sine_segment(440.0, 0.1, 0.5)
    wav = _to_wav(pcm)
    _check("wav_container: starts with RIFF",    wav[:4] == b'RIFF')
    _check("wav_container: has WAVE marker",      wav[8:12] == b'WAVE')
    buf = io.BytesIO(wav)
    with wave.open(buf, 'rb') as wf:
        _check("wav_container: mono",             wf.getnchannels() == 1)
        _check("wav_container: 16-bit",           wf.getsampwidth() == 2)
        _check("wav_container: correct sample rate", wf.getframerate() == SAMPLE_RATE)
    assert wav[:4] == b'RIFF'


def test_tone_composers():
    for severity, make_fn in [
        ("INFO",      _make_info_tone),
        ("WARNING",   _make_warning_tone),
        ("CRITICAL",  _make_critical_tone),
        ("EMERGENCY", _make_emergency_tone),
    ]:
        tone = make_fn(0.8)
        _check(f"{severity}_tone: returns bytes",    isinstance(tone, bytes))
        _check(f"{severity}_tone: non-empty",        len(tone) > 100)
        _check(f"{severity}_tone: valid WAV header", tone[:4] == b'RIFF')

        dur = _wav_duration(tone)
        exp = {"INFO": 0.3, "WARNING": 0.5, "CRITICAL": 0.8, "EMERGENCY": 1.0}[severity]
        _check(f"{severity}_tone: duration ≈ {exp}s",
               abs(dur - exp) < exp * 0.25,
               f"got {dur:.2f}s, expected ~{exp}s")
        assert tone[:4] == b'RIFF'


def test_tone_ordering():
    di = _wav_duration(_make_info_tone(0.8))
    dw = _wav_duration(_make_warning_tone(0.8))
    dc = _wav_duration(_make_critical_tone(0.8))
    de = _wav_duration(_make_emergency_tone(0.8))
    _check("tone_ordering: warning > info",       dw > di)
    _check("tone_ordering: critical > warning",   dc > dw)
    _check("tone_ordering: emergency >= critical", de >= dc)
    assert dw > di and dc > dw


def test_play_tone_bytes():
    for sev in ("INFO", "WARNING", "CRITICAL", "EMERGENCY"):
        b = play_tone_bytes(sev, {"tts_tone_volume": 0.8})
        _check(f"play_tone_bytes({sev}): valid WAV", b[:4] == b'RIFF')
        assert b[:4] == b'RIFF'
    b = play_tone_bytes("UNKNOWN", {})
    _check("play_tone_bytes(UNKNOWN): falls back to INFO",
           b[:4] == b'RIFF' and len(b) > 0)


def test_ensure_tones():
    import platforms.linux.tts_tones as _tones_mod
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_dir = _tones_mod.TONE_DIR
        _tones_mod.TONE_DIR = Path(tmpdir) / "tones"
        try:
            result = _tones_mod.ensure_tones(0.8)
            _check("ensure_tones: returns True",   result)
            _check("ensure_tones: creates all 4 files",
                   all((_tones_mod.TONE_DIR / fn).exists() for fn in TONE_FILES.values()))
            _check("tones_exist: True after ensure",  _tones_mod.tones_exist())
            result2 = _tones_mod.ensure_tones(0.8, force=True)
            _check("ensure_tones(force=True): returns True", result2)
            assert result and result2
        finally:
            _tones_mod.TONE_DIR = orig_dir


def test_voice_catalog():
    _check("PIPER_VOICES: ryan-high is present",   "en_US-ryan-high" in PIPER_VOICES)
    _check("DEFAULT_VOICE is ryan-high",            DEFAULT_VOICE == "en_US-ryan-high")
    _check("BACKUP_VOICE is lessac-medium",         BACKUP_VOICE == "en_US-lessac-medium")
    _check("PIPER_VOICES: all entries have 3-tuple",
           all(isinstance(v, tuple) and len(v) == 3 and isinstance(v[1], int) and 1 <= v[1] <= 5
               for v in PIPER_VOICES.values()))
    assert DEFAULT_VOICE == "en_US-ryan-high"


def test_voice_aliases():
    _check("alias: ryan → en_US-ryan-high",       resolve_voice_alias("ryan") == "en_US-ryan-high")
    _check("alias: lessac → en_US-lessac-medium", resolve_voice_alias("lessac") == "en_US-lessac-medium")
    _check("alias: unknown passthrough",           resolve_voice_alias("en_US-amy-medium") == "en_US-amy-medium")
    _check("alias: case insensitive",              resolve_voice_alias("RYAN") == "en_US-ryan-high")
    for short, full in VOICE_ALIASES.items():
        _check(f"alias: {short} resolves to known voice", full in PIPER_VOICES, f"{full} not in PIPER_VOICES")
    assert resolve_voice_alias("ryan") == "en_US-ryan-high"


def test_active_voice():
    _check("active_voice: default when no config",  _active_voice({}) == DEFAULT_VOICE)
    _check("active_voice: reads tts_voice_name",
           _active_voice({"tts_voice_name": "en_US-amy-medium"}) == "en_US-amy-medium")
    assert _active_voice({}) == DEFAULT_VOICE


def test_voice_path():
    p = _get_voice_path("en_US-ryan-high")
    _check("get_voice_path: returns Path",   isinstance(p, Path))
    _check("get_voice_path: correct name",   p.name == "en_US-ryan-high.onnx")
    _check("get_voice_path: in piper dir",   "piper" in str(p))
    assert p.name == "en_US-ryan-high.onnx"


def test_last_messages():
    with _last_msg_lock:
        _last_messages.clear()
    _store_message("Black ice on I-76", "CRITICAL")
    _store_message("Bridge freeze warning", "WARNING")
    _store_message("Weigh station closed", "INFO")
    msgs = get_last_messages()
    _check("last_messages: stores 3 messages",  len(msgs) == 3)
    _check("last_messages: newest is last",     msgs[-1]["text"] == "Weigh station closed")
    _check("last_messages: severity preserved", msgs[0]["severity"] == "CRITICAL")
    _check("last_messages: has timestamp",      "ts" in msgs[0] and msgs[0]["ts"] > 0)
    _store_message("Fourth message", "WARNING")
    msgs2 = get_last_messages()
    _check("last_messages: capped at 3",     len(msgs2) == 3)
    _check("last_messages: oldest dropped",  msgs2[0]["text"] == "Bridge freeze warning")
    _check("last_messages: newest appended", msgs2[-1]["text"] == "Fourth message")
    assert len(msgs2) == 3


def test_emergency_priority():
    _check("priority: EMERGENCY highest",
           _PRIORITY.get("EMERGENCY", 99) < _PRIORITY.get("CRITICAL", 99))
    _check("priority: CRITICAL > WARNING", _PRIORITY["CRITICAL"] < _PRIORITY["WARNING"])
    _check("priority: WARNING > INFO",     _PRIORITY["WARNING"]  < _PRIORITY["INFO"])
    assert _PRIORITY["EMERGENCY"] < _PRIORITY["CRITICAL"]


def test_tone_file_mapping():
    _check("TONE_FILES: 4 severities",  len(TONE_FILES) == 4)
    for s in ("INFO", "WARNING", "CRITICAL", "EMERGENCY"):
        _check(f"TONE_FILES: has {s}", s in TONE_FILES)
    assert len(TONE_FILES) == 4


def test_engine_info_keys():
    info = get_engine_info({})
    for key in ("engine", "voice", "stars", "star_str", "degraded"):
        _check(f"get_engine_info: has key '{key}'", key in info)
    _check("get_engine_info: stars is int",    isinstance(info["stars"], int))
    _check("get_engine_info: stars 0-5",       0 <= info["stars"] <= 5)
    _check("get_engine_info: degraded is bool", isinstance(info["degraded"], bool))
    assert "engine" in info and isinstance(info["stars"], int)


# ─────────────────────────────────────────────────────────────────────────────

def run_all():
    """Run all tests and return (passed, failed)."""
    global _passed, _failed
    _passed = _failed = 0

    test_sine_segment()
    test_silence()
    test_wav_container()
    test_tone_composers()
    test_tone_ordering()
    test_play_tone_bytes()
    test_ensure_tones()
    test_voice_catalog()
    test_voice_aliases()
    test_active_voice()
    test_voice_path()
    test_last_messages()
    test_emergency_priority()
    test_tone_file_mapping()
    test_engine_info_keys()

    return _passed, _failed


if __name__ == "__main__":
    p, f = run_all()
    print()
    print("=" * 50)
    print(f"  tones: {p} passed, {f} failed")
    if not f:
        print("  All tone/voice/repeat tests passed.")
    else:
        print(f"  ❌ {f} test(s) failed.")
    print("=" * 50)
    sys.exit(1 if f else 0)
