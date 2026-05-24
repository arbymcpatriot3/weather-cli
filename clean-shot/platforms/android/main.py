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
_REPO_ROOT  = Path(__file__).resolve().parent.parent.parent   # weather-cli-2.0.0/
_CLEAN_SHOT = _REPO_ROOT / "clean-shot"

for _p in [str(_REPO_ROOT), str(_CLEAN_SHOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

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

# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    if _MISSING:
        print(f"  ℹ  Missing packages: {', '.join(_MISSING)}")
        print("     Run: pkg install python && pip install " + " ".join(_MISSING))
        print()

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
