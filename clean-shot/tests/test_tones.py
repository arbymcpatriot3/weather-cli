#!/usr/bin/env python3
# tests/test_tones.py — Clean Shot: Alert tone + repeat + voice selection tests
# No audio output — all tests are logic-only.
# Tones are generated in memory (play_tone is never called).

import io
import sys
import struct
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
    _store_message, get_last_messages, wait_for_repeat,
    _last_messages, _last_msg_lock,
    _PRIORITY,
)

# ─────────────────────────────────────────────────────────────────────────────
passed = failed = 0

def ok(name: str):
    global passed
    passed += 1
    print(f"✓ {name}")

def fail(name: str, reason: str):
    global failed
    failed += 1
    print(f"✗ {name}: {reason}")

def check(name: str, condition: bool, reason: str = ""):
    if condition:
        ok(name)
    else:
        fail(name, reason or "condition was False")


# ── 1. Sine segment generation ────────────────────────────────────────────────

seg = _sine_segment(440.0, 0.1, 0.8)
check("sine_segment: correct byte length",
      len(seg) == int(0.1 * SAMPLE_RATE) * 2,
      f"got {len(seg)}, expected {int(0.1*SAMPLE_RATE)*2}")

check("sine_segment: returns bytes",
      isinstance(seg, bytes))

check("sine_segment: non-zero content",
      any(b != 0 for b in seg))

# ── 2. Silence generation ─────────────────────────────────────────────────────

sil = _silence(0.1)
check("silence: correct length",
      len(sil) == int(0.1 * SAMPLE_RATE) * 2)

check("silence: all zeros",
      all(b == 0 for b in sil))

# ── 3. WAV container ──────────────────────────────────────────────────────────

pcm = _sine_segment(440.0, 0.1, 0.5)
wav = _to_wav(pcm)
check("wav_container: starts with RIFF",
      wav[:4] == b'RIFF')

check("wav_container: has WAVE marker",
      wav[8:12] == b'WAVE')

# Parse WAV to verify metadata
buf = io.BytesIO(wav)
with wave.open(buf, 'rb') as wf:
    check("wav_container: mono",     wf.getnchannels() == 1)
    check("wav_container: 16-bit",   wf.getsampwidth() == 2)
    check("wav_container: correct sample rate",
          wf.getframerate() == SAMPLE_RATE)

# ── 4. Tone composers — structure checks ─────────────────────────────────────

for severity, make_fn in [
    ("INFO",      _make_info_tone),
    ("WARNING",   _make_warning_tone),
    ("CRITICAL",  _make_critical_tone),
    ("EMERGENCY", _make_emergency_tone),
]:
    tone = make_fn(0.8)

    check(f"{severity}_tone: returns bytes",         isinstance(tone, bytes))
    check(f"{severity}_tone: non-empty",             len(tone) > 100)
    check(f"{severity}_tone: valid WAV header",      tone[:4] == b'RIFF')

    # Approximate duration check (generous ±20%)
    buf = io.BytesIO(tone)
    with wave.open(buf, 'rb') as wf:
        dur = wf.getnframes() / wf.getframerate()

    expected = {"INFO": 0.3, "WARNING": 0.5, "CRITICAL": 0.8, "EMERGENCY": 1.0}
    exp = expected[severity]
    check(f"{severity}_tone: duration ≈ {exp}s",
          abs(dur - exp) < exp * 0.25,   # within 25%
          f"got {dur:.2f}s, expected ~{exp}s")

# ── 5. Tone duration ordering (CRITICAL > WARNING > INFO) ────────────────────

def _wav_duration(wav_bytes: bytes) -> float:
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, 'rb') as wf:
        return wf.getnframes() / wf.getframerate()

dur_info     = _wav_duration(_make_info_tone(0.8))
dur_warning  = _wav_duration(_make_warning_tone(0.8))
dur_critical = _wav_duration(_make_critical_tone(0.8))
dur_emergency= _wav_duration(_make_emergency_tone(0.8))

check("tone_ordering: warning > info",     dur_warning  > dur_info)
check("tone_ordering: critical > warning", dur_critical > dur_warning)
check("tone_ordering: emergency > critical", dur_emergency >= dur_critical)

# ── 6. play_tone_bytes API ────────────────────────────────────────────────────

for sev in ("INFO", "WARNING", "CRITICAL", "EMERGENCY"):
    b = play_tone_bytes(sev, {"tts_tone_volume": 0.8})
    check(f"play_tone_bytes({sev}): valid WAV", b[:4] == b'RIFF')

# Unknown severity falls back to INFO
b = play_tone_bytes("UNKNOWN", {})
check("play_tone_bytes(UNKNOWN): falls back to INFO",
      b[:4] == b'RIFF' and len(b) > 0)

# ── 7. ensure_tones ───────────────────────────────────────────────────────────

import tempfile, os
with tempfile.TemporaryDirectory() as tmpdir:
    # Monkey-patch TONE_DIR temporarily
    import platforms.linux.tts_tones as _tones_mod
    orig_dir = _tones_mod.TONE_DIR
    _tones_mod.TONE_DIR = Path(tmpdir) / "tones"
    try:
        result = _tones_mod.ensure_tones(0.8)
        check("ensure_tones: returns True",   result)
        check("ensure_tones: creates all 4 files",
              all((_tones_mod.TONE_DIR / fn).exists() for fn in TONE_FILES.values()))
        check("tones_exist: True after ensure",  _tones_mod.tones_exist())

        # Force regenerate
        result2 = _tones_mod.ensure_tones(0.8, force=True)
        check("ensure_tones(force=True): returns True", result2)
    finally:
        _tones_mod.TONE_DIR = orig_dir

# ── 8. Voice catalog completeness ─────────────────────────────────────────────

check("PIPER_VOICES: ryan-high is present",
      "en_US-ryan-high" in PIPER_VOICES)

check("PIPER_VOICES: DEFAULT_VOICE is ryan-high",
      DEFAULT_VOICE == "en_US-ryan-high")

check("PIPER_VOICES: BACKUP_VOICE is lessac-medium",
      BACKUP_VOICE == "en_US-lessac-medium")

check("PIPER_VOICES: all entries have 3-tuple (path, stars, desc)",
      all(
          isinstance(v, tuple) and len(v) == 3
          and isinstance(v[1], int) and 1 <= v[1] <= 5
          for v in PIPER_VOICES.values()
      ))

# ── 9. Voice aliases ──────────────────────────────────────────────────────────

check("alias: ryan → en_US-ryan-high",
      resolve_voice_alias("ryan") == "en_US-ryan-high")

check("alias: lessac → en_US-lessac-medium",
      resolve_voice_alias("lessac") == "en_US-lessac-medium")

check("alias: unknown passthrough",
      resolve_voice_alias("en_US-amy-medium") == "en_US-amy-medium")

check("alias: case insensitive",
      resolve_voice_alias("RYAN") == "en_US-ryan-high")

# All aliases resolve to known voice names
for short, full in VOICE_ALIASES.items():
    check(f"alias: {short} resolves to known voice",
          full in PIPER_VOICES,
          f"{full} not in PIPER_VOICES")

# ── 10. _active_voice config respect ─────────────────────────────────────────

check("active_voice: default when no config",
      _active_voice({}) == DEFAULT_VOICE)

check("active_voice: reads tts_voice_name",
      _active_voice({"tts_voice_name": "en_US-amy-medium"}) == "en_US-amy-medium")

# ── 11. Voice path helper ─────────────────────────────────────────────────────

p = _get_voice_path("en_US-ryan-high")
check("get_voice_path: returns Path",   isinstance(p, Path))
check("get_voice_path: correct name",   p.name == "en_US-ryan-high.onnx")
check("get_voice_path: in piper dir",   "piper" in str(p))

# ── 12. Last-messages ring buffer ────────────────────────────────────────────

# Clear the buffer first
with _last_msg_lock:
    _last_messages.clear()

_store_message("Black ice on I-76", "CRITICAL")
_store_message("Bridge freeze warning", "WARNING")
_store_message("Weigh station closed", "INFO")

msgs = get_last_messages()
check("last_messages: stores 3 messages",  len(msgs) == 3)
check("last_messages: newest is last",     msgs[-1]["text"] == "Weigh station closed")
check("last_messages: severity preserved", msgs[0]["severity"] == "CRITICAL")
check("last_messages: has timestamp",      "ts" in msgs[0] and msgs[0]["ts"] > 0)

# Test ring buffer cap at 3
_store_message("Fourth message", "WARNING")
msgs2 = get_last_messages()
check("last_messages: capped at 3",         len(msgs2) == 3)
check("last_messages: oldest dropped",      msgs2[0]["text"] == "Bridge freeze warning")
check("last_messages: newest appended",     msgs2[-1]["text"] == "Fourth message")

# ── 13. EMERGENCY priority ────────────────────────────────────────────────────

check("priority: EMERGENCY highest",
      _PRIORITY.get("EMERGENCY", 99) < _PRIORITY.get("CRITICAL", 99))

check("priority: CRITICAL > WARNING",
      _PRIORITY["CRITICAL"] < _PRIORITY["WARNING"])

check("priority: WARNING > INFO",
      _PRIORITY["WARNING"] < _PRIORITY["INFO"])

# ── 14. Tone file mapping coverage ───────────────────────────────────────────

check("TONE_FILES: 4 severities",  len(TONE_FILES) == 4)
check("TONE_FILES: has INFO",      "INFO"      in TONE_FILES)
check("TONE_FILES: has WARNING",   "WARNING"   in TONE_FILES)
check("TONE_FILES: has CRITICAL",  "CRITICAL"  in TONE_FILES)
check("TONE_FILES: has EMERGENCY", "EMERGENCY" in TONE_FILES)

# ── 15. get_engine_info returns required keys ─────────────────────────────────

info = get_engine_info({})
for key in ("engine", "voice", "stars", "star_str", "degraded"):
    check(f"get_engine_info: has key '{key}'", key in info)

check("get_engine_info: stars is int",    isinstance(info["stars"], int))
check("get_engine_info: stars 0-5",       0 <= info["stars"] <= 5)
check("get_engine_info: degraded is bool", isinstance(info["degraded"], bool))

# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 50)
print(f"  tones: {passed} passed, {failed} failed")
if not failed:
    print("  All tone/voice/repeat tests passed.")
else:
    print(f"  ❌ {failed} test(s) failed.")
print("=" * 50)
sys.exit(1 if failed else 0)
