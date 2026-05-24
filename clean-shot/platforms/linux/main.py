#!/usr/bin/env python3
# platforms/linux/main.py — Clean Shot: Linux unified entry point
#
# Run:  python3 platforms/linux/main.py
#       python3 platforms/linux/main.py watch
#       python3 platforms/linux/main.py --location "Memphis TN"
#
# With no arguments, shows the full unified view:
#   Current weather + Active alerts + DOT/511 + Community hazards +
#   Parking runway + HOS status + Flash/beep on critical items
#
# Passes all command-line arguments through to core.weather.main()
# so every cleanshot command is supported.

import sys
import os
from pathlib import Path

# ── sys.path: allow running from any working directory ────────────────────────
_REPO_ROOT   = Path(__file__).resolve().parent.parent.parent   # weather-cli-2.0.0/
_CLEAN_SHOT  = _REPO_ROOT / "clean-shot"

for _p in [str(_REPO_ROOT), str(_CLEAN_SHOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Pre-flight: report any missing optional dependencies ──────────────────────
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
# Anything else is passed as --location to avoid geocoding command names
# (e.g. "parking" → "Parking, EG" or "doctor" → "Doctor Mora, MX").
_KNOWN_COMMANDS = {
    # Core display
    "full", "simple", "compact", "watch", "json", "map",
    # Weather / alerts
    "alerts", "test-alerts", "testalerts", "alerts-test",
    "morning",
    # Trucking features
    "parking", "fuel", "route", "pretrip",
    # TTS / voice
    "test-tts", "testtts", "tts-test", "fix-voice", "fixvoice", "voices",
    # System / meta
    "doctor", "help", "settings", "version", "--version", "-v",
    "update", "setup", "replaces",
    # Session control
    "quit", "exit",
}


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if _MISSING:
        print(f"  ℹ  Optional packages not installed: {', '.join(_MISSING)}")
        print("     Run: pip install " + " ".join(_MISSING))
        print()

    # Guard: if the first positional arg is not a known command, rewrite it
    # as --location so core.weather.main() never falls through to the
    # geocode fallback for command-like words.
    # Example: `cleanshot "Memphis TN"` → `cleanshot --location "Memphis TN"`
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
