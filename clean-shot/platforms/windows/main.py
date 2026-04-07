#!/usr/bin/env python3
# platforms/windows/main.py — Clean Shot: Windows entry point

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.weather import main

if __name__ == "__main__":
    main()
