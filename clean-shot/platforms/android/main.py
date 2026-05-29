#!/usr/bin/env python3
# platforms/android/main.py — Clean Shot: Android / Termux entry point
#
# Run:  python3 platforms/android/main.py
#       python3 platforms/android/main.py watch
#       python3 platforms/android/main.py --location "Memphis TN"
#
# Termux sets TMPDIR correctly when termux-api is installed.
# This file sets it as a fallback in case it's missing.

import sys
import os
from pathlib import Path

# ── Termux: ensure TMPDIR is set before any module imports cache paths ─────────
if not os.environ.get("TMPDIR"):
    _prefix = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
    os.environ["TMPDIR"] = f"{_prefix}/tmp"

# ── sys.path: allow running from any working directory ─────────────────────────
# __file__ = clean-shot/platforms/android/main.py
# parent.parent.parent = clean-shot/  ← package root where core/, display/, etc. live
_CLEAN_SHOT_DIR = Path(__file__).resolve().parent.parent.parent

if str(_CLEAN_SHOT_DIR) not in sys.path:
    sys.path.insert(0, str(_CLEAN_SHOT_DIR))

# ── Pre-flight: report any missing optional dependencies ───────────────────────
_MISSING = []
try:
    import colorama  # noqa: F401
except ImportError:
    _MISSING.append("colorama")
try:
    import requests  # noqa: F401
except ImportError:
    _MISSING.append("requests")

# ── Known CLI commands — checked BEFORE any location lookup ───────────────────
# If a positional arg matches one of these it is routed as a command.
# Anything else is passed as --location to avoid geocoding command names.
_KNOWN_COMMANDS = {
    "full", "simple", "compact", "watch", "json", "map",
    "alerts", "test-alerts", "testalerts", "alerts-test",
    "morning",
    "parking", "fuel", "route", "pretrip",
    "test-tts", "testtts", "tts-test", "fix-voice", "fixvoice", "voices",
    "doctor", "help", "settings", "version", "--version", "-v",
    "update", "setup", "replaces",
    "quit", "exit",
}


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    if _MISSING:
        print(f"  ℹ  Missing packages: {', '.join(_MISSING)}")
        print("     Run: pkg install python && pip install " + " ".join(_MISSING))
        print()

    # Guard: if the first positional arg is not a known command, rewrite as --location
    if len(sys.argv) >= 2:
        first = sys.argv[1]
        if not first.startswith("-") and first.lower() not in _KNOWN_COMMANDS:
            sys.argv = [sys.argv[0], "--location", first] + sys.argv[2:]

    try:
        from core.weather import main as _weather_main
        _weather_main()
    except KeyboardInterrupt:
        print("\n  Clean Shot — drive safe out there.")
        sys.exit(0)
    except Exception as exc:
        if os.environ.get("CLEANSHOT_DEBUG"):
            import traceback
            traceback.print_exc()
        else:
            print("\n  Something went wrong.")
            print("  Please contact: support@cleanshothq.com")
            print("  We'll fix it fast.")
            print("  (Set CLEANSHOT_DEBUG=1 for details)")
        sys.exit(1)


if __name__ == "__main__":
    main()
