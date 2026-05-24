#!/usr/bin/env python3
# platforms/ios/main.py — Clean Shot: iOS entry point (Pythonista / Pyto)
# Runs under Pythonista 3 or Pyto on iPhone/iPad.
# UI is the same ASCII terminal output, rendered in the app's console.
# TODO: implement iOS-specific startup in module sprint

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.weather import main

if __name__ == "__main__":
    main()
