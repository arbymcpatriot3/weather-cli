# Build-only entry point for PyInstaller — NOT committed, not in the installer.
# sys.path is patched here so static analysis resolves all local packages.
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

# Explicit top-level imports give PyInstaller's static scanner a guaranteed path
# to every local package — no pathex guesswork needed.
import display
import display.full
import display.display_alerts
import display.route
import display.replaces
import display.glance
import display.themes
import display.dashboard
import core
import core.weather
import core.config
import core.api
import core.cache
import core.alerts
import core.tts
import core.gps
import core.parse
import core.hazards
import core.dot511
import core.parking
import core.hos
import core.subscription
import core.referral
import core.updater
import core.i18n
import core.i18n.translator
import claude
import claude.prompts
import claude.parser
import platforms.windows.tts_windows
import platforms.windows.gps_windows

# Hand off to the real Windows entry point
from platforms.windows.main import main
if __name__ == '__main__':
    main()
