#!/usr/bin/env python3
# platforms/linux/main.py — Clean Shot: Linux/macOS unified entry point
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
#
# Also used by macOS (install.sh runs this file directly).

import sys
import os
from pathlib import Path

# ── sys.path: allow running from any working directory ────────────────────────
# __file__ = clean-shot/platforms/linux/main.py
# parent.parent.parent  = clean-shot/   ← package root where core/, display/, etc. live
_CLEAN_SHOT_DIR = Path(__file__).resolve().parent.parent.parent

if str(_CLEAN_SHOT_DIR) not in sys.path:
    sys.path.insert(0, str(_CLEAN_SHOT_DIR))

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

# ── Console size: grow to 120×50 if the terminal is too small ────────────────
def _ensure_console_size(min_cols: int = 120, min_rows: int = 50) -> None:
    """
    Attempt to grow the terminal to at least min_cols × min_rows.
    Uses ANSI xterm resize sequence first (works in most terminal emulators),
    then falls back to `resize` (xterm-utils), then `stty`.
    Silently no-ops on Android/iOS where the terminal window is app-controlled.
    """
    # Skip on mobile — Termux/iSH users control window size through the app
    if os.environ.get("TERMUX_VERSION") or "com.termux" in os.environ.get("PREFIX", ""):
        return

    try:
        import shutil
        current = shutil.get_terminal_size(fallback=(0, 0))
        if current.columns >= min_cols and current.lines >= min_rows:
            return   # already big enough

        # ANSI xterm resize: ESC [ 8 ; rows ; cols t
        sys.stdout.write(f"\033[8;{min_rows};{min_cols}t")
        sys.stdout.flush()
    except Exception:
        pass

    # stty fallback — sets kernel TTY size record (most terminals honour it)
    try:
        import subprocess
        subprocess.run(
            ["stty", f"cols {min_cols}", f"rows {min_rows}"],
            capture_output=True,
        )
    except Exception:
        pass


# ── Continuous monitor (text-only, no msvcrt — Ctrl+C to quit) ───────────────

def _continuous_monitor_unix(interval_minutes: int = 5) -> None:
    """
    Continuous monitoring for Linux/macOS/Android.
    No non-blocking key input — press Ctrl+C to exit.
    """
    import time as _time
    import os as _os
    import json as _json
    import hashlib as _hl

    try:
        from core.config import get_config
        from core.weather import main as _weather_main
    except ImportError:
        print("  Continuous mode unavailable — core modules not loaded.")
        return

    print()
    print(f"  🔄 Continuous Monitor — refreshing every {interval_minutes} min")
    print("  Press Ctrl+C to stop.")
    _time.sleep(1)

    while True:
        try:
            _os.system("clear")
            print(f"  {'═' * 56}")
            print(f"  🔄  CONTINUOUS MODE  [{interval_minutes} min]  —  Ctrl+C to quit")
            print(f"  {'═' * 56}")
            print()

            import sys as _sys
            saved = _sys.argv[:]
            _sys.argv = ["cleanshot"]
            try:
                _weather_main()
            except SystemExit:
                pass
            finally:
                _sys.argv = saved

            for remaining in range(interval_minutes * 60, 0, -1):
                m, s = divmod(remaining, 60)
                print(f"\r  Next refresh in {m:02d}:{s:02d}   ", end="", flush=True)
                _time.sleep(1)
            print()

        except KeyboardInterrupt:
            print("\n  Continuous mode ended. Drive safe.")
            return


# ── Known CLI commands — checked BEFORE any location lookup ───────────────────
# If a positional arg matches one of these it is routed as a command.
# Anything else is passed as --location to avoid geocoding command names
# (e.g. "parking" → "Parking, EG" or "doctor" → "Doctor Mora, MX").
_KNOWN_COMMANDS = {
    # Core display
    "full", "simple", "compact", "watch", "monitor", "continuous", "json", "map",
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
    _ensure_console_size()

    if _MISSING:
        print(f"  ℹ  Optional packages not installed: {', '.join(_MISSING)}")
        print("     Run: pip install " + " ".join(_MISSING))
        print()

    # Guard: if the first positional arg is not a known command, rewrite it
    # as --location so core.weather.main() never falls through to the
    # geocode fallback for command-like words.
    # Example: `cleanshot "Memphis TN"` → `cleanshot --location "Memphis TN"`
    if len(sys.argv) >= 2:
        first = sys.argv[1].lower()
        if first in ("monitor", "continuous", "watch"):
            mins = 5
            if len(sys.argv) >= 3 and sys.argv[2].isdigit():
                mins = int(sys.argv[2])
            _continuous_monitor_unix(mins)
            return
        if not sys.argv[1].startswith("-") and first not in _KNOWN_COMMANDS:
            sys.argv = [sys.argv[0], "--location", sys.argv[1]] + sys.argv[2:]

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
