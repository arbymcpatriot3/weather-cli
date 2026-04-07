#!/usr/bin/env python3
# platforms/linux/main.py — Clean Shot: Linux entry point
# Adds the clean-shot package root to sys.path, then delegates to core.weather.

import sys
from pathlib import Path

# Allow "python platforms/linux/main.py" from any cwd
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.weather import main

if __name__ == "__main__":
    main()
