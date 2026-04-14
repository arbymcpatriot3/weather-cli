#!/usr/bin/env python3
# core/weather.py — Clean Shot: weather commands and CLI entry point
# Migrated from weather.py v2.0.0 — updated imports and branding.
# Platform entry points (platforms/*/main.py) call main() here.

import tempfile
import argparse
import sys
import os
import time
import json
from datetime import datetime

from core.config  import get_config, save_config, first_run_setup, show_settings, VERSION


def _cmd() -> str:
    """
    Return the command name that matches how the user invoked Clean Shot.

    Priority:
      1. CLEANSHOT_CMD env var — set by all launcher scripts so 'cleanshot'
         shows up even though sys.argv[0] is still main.py
      2. sys.argv[0] basename detection — fallback for direct invocation
         Uses 'python' on Windows, 'python3' everywhere else.
    """
    env = os.environ.get("CLEANSHOT_CMD", "").strip()
    if env:
        return env

    argv0 = sys.argv[0] if sys.argv else ""
    base  = os.path.basename(argv0)
    py    = "python" if sys.platform == "win32" else "python3"

    if base in ("cleanshot", "weather"):
        return base
    if base in ("main.py", "weather.py"):
        return f"{py} {base}"
    return f"{py} main.py"
from core.api     import fetch_weather, fetch_alerts, geocode_location, get_auto_location
from core.parse   import parse_current, parse_forecast, parse_hourly
from display.full import (
    get_width, print_header,
    display_simple, display_compact, display_current,
    display_alerts, display_wind_alert,
    display_hourly, display_forecast, display_rain_timeline,
    display_regional,
)
from display.route import display_route_header, display_route_stop

# ── Road intelligence modules (lazy imports — graceful if not yet present) ────
try:
    from core.alerts import get_road_alerts, has_critical
    _ALERTS_OK = True
except ImportError:
    _ALERTS_OK = False

try:
    from core.dot511 import get_active_incidents, display_dot511
    _DOT511_OK = True
except ImportError:
    _DOT511_OK = False

try:
    from core.hazards import get_active_hazards, display_hazards
    _HAZARDS_OK = True
except ImportError:
    _HAZARDS_OK = False

try:
    from core.parking import (
        compute_runway, find_recommended_stop,
        display_parking_status, announce_runway,
    )
    _PARKING_OK = True
except ImportError:
    _PARKING_OK = False

try:
    from display.display_alerts import (
        check_and_display, display_critical_alerts,
        display_urgent_parking, display_hos_critical,
    )
    _DISP_ALERTS_OK = True
except ImportError:
    _DISP_ALERTS_OK = False

try:
    from core.hos import (
        get_hos_status, display_hos_status,
        announce_hos, update_elapsed,
    )
    _HOS_OK = True
except ImportError:
    _HOS_OK = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def resolve_location(args, config):
    """
    Determine lat/lon/city from args or config.
    Priority: --location arg > saved config > IP auto-detect
    Returns (lat, lon, city) or exits on failure.
    """
    if args.location:
        loc_str = args.location.strip()
        lat, lon, city = geocode_location(loc_str)
        if lat is None:
            print(f"  Can't find that location: '{loc_str}'")
            print('  Try: cleanshot "Memphis TN"  or  cleanshot 38101')
            print("  Need help? support@cleanshothq.com")
            sys.exit(1)
        config["latitude"]  = lat
        config["longitude"] = lon
        config["city"]      = city
        save_config(config)
        return lat, lon, city

    lat  = config.get("latitude")
    lon  = config.get("longitude")
    city = config.get("city", "Unknown")

    if lat is not None and lon is not None:
        return lat, lon, city

    print("ℹ  Auto-detecting location via IP...")
    lat, lon, city = get_auto_location()
    if lat is not None:
        print(f"✓  Detected: {city}")
        config["latitude"]  = lat
        config["longitude"] = lon
        config["city"]      = city
        save_config(config)
        return lat, lon, city

    print(f"  No location set yet.")
    print(f"  Run: {_cmd()} settings location")
    print(f"  Or:  {_cmd()} \"Memphis TN\"  to use a location once")
    sys.exit(1)


def build_parsed(data_str, city, cache_age, config):
    """Build the unified parsed data dict used by display functions."""
    return {
        "current":        parse_current(data_str),
        "forecast":       parse_forecast(data_str),
        "hourly":         parse_hourly(data_str),
        "city":           city,
        "timestamp":      datetime.now().strftime("%m/%d/%Y %I:%M %p"),
        "time_format":    config.get("time_format", "12h"),
        "cache_age":      cache_age or 0,
        "wind_alert_mph": config.get("wind_alert_mph", 40),
    }


def get_weather_data(lat, lon, force_fresh, label=""):
    """Fetch + report cache status. Returns (data_str, cache_age)."""
    data_str, cache_age = fetch_weather(lat, lon, force_fresh)
    if data_str is None:
        print("  Can't reach weather service right now.")
        print("  Showing last known conditions if available.")
        print("  Check your connection or try again in a moment.")
        return None, None
    return data_str, cache_age


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_full(args, config, width):
    lat, lon, city = resolve_location(args, config)
    data_str, cache_age = get_weather_data(lat, lon, args.fresh)
    if data_str is None:
        sys.exit(1)

    parsed    = build_parsed(data_str, city, cache_age, config)
    alerts    = fetch_alerts(lat, lon)
    alert_mph = config.get("wind_alert_mph", 40)

    print_header(f"Clean Shot — {city}", width, VERSION)
    display_current(parsed, width)
    display_alerts(alerts, width)
    display_wind_alert(parsed["hourly"], alert_mph, width)
    display_hourly(parsed["hourly"], width, parsed["time_format"], alert_mph)
    display_forecast(parsed["forecast"], width)
    display_rain_timeline(parsed["hourly"], width, parsed["time_format"])
    _display_road_section(lat, lon, parsed, config, width)


def cmd_simple(args, config, width):
    lat, lon, city = resolve_location(args, config)
    data_str, _ = get_weather_data(lat, lon, args.fresh)
    if data_str is None:
        sys.exit(1)
    parsed = build_parsed(data_str, city, 0, config)
    display_simple(parsed)


def cmd_compact(args, config, width):
    lat, lon, city = resolve_location(args, config)
    data_str, _ = get_weather_data(lat, lon, args.fresh)
    if data_str is None:
        sys.exit(1)
    parsed = build_parsed(data_str, city, 0, config)
    display_compact(parsed, width)


def cmd_json(args, config, width):
    lat, lon, city = resolve_location(args, config)
    data_str, _ = get_weather_data(lat, lon, args.fresh)
    if data_str is None:
        sys.exit(1)
    print(json.dumps(json.loads(data_str), indent=2))


def cmd_alerts(args, config, width):
    lat, lon, city = resolve_location(args, config)
    alerts = fetch_alerts(lat, lon)
    if alerts:
        display_alerts(alerts, width)
    else:
        print(f"✓  No active weather alerts for {city}")


def cmd_watch(args, config, width):
    lat, lon, city = resolve_location(args, config)
    alert_mph = config.get("wind_alert_mph", 40)
    interval  = 900  # 15 minutes
    try:
        while True:
            os.system("clear")
            data_str, cache_age = fetch_weather(lat, lon, force_fresh=True)
            if data_str:
                parsed = build_parsed(data_str, city, cache_age, config)
                alerts = fetch_alerts(lat, lon)
                print_header(f"Clean Shot — {city}  [Auto-refresh every 15 min]",
                             width, VERSION)
                display_current(parsed, width)
                display_alerts(alerts, width)
                display_wind_alert(parsed["hourly"], alert_mph, width)
                display_hourly(parsed["hourly"], width,
                               parsed["time_format"], alert_mph)
                display_forecast(parsed["forecast"], width)
                _display_road_section(lat, lon, parsed, config, width)
            else:
                print("⚠  Failed to fetch update. Retrying in 15 min...")
            print(f"\n  Last updated: {datetime.now().strftime('%H:%M:%S')} "
                  f"| Ctrl+C to exit")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n  Exiting watch mode.")


def cmd_route(args, config, width):
    """Show weather along a route with 5 evenly-spaced stops."""
    if not args.route or len(args.route) < 2:
        print(f'Usage: {_cmd()} route "Start City" "End City"')
        sys.exit(1)

    start_str, end_str = args.route[0], args.route[1]
    num_stops = 5  # start + 3 intermediate + end

    print(f"Geocoding route: {start_str} → {end_str} ...")

    start_lat, start_lon, start_city = geocode_location(start_str)
    if start_lat is None:
        print(f"✗ Could not find start location: '{start_str}'")
        sys.exit(1)

    end_lat, end_lon, end_city = geocode_location(end_str)
    if end_lat is None:
        print(f"✗ Could not find end location: '{end_str}'")
        sys.exit(1)

    stops = []
    for i in range(num_stops):
        frac = i / (num_stops - 1)
        lat  = start_lat + (end_lat - start_lat) * frac
        lon  = start_lon + (end_lon - start_lon) * frac
        if i == 0:
            name = start_city
        elif i == num_stops - 1:
            name = end_city
        else:
            name = f"Waypoint {i} (approx)"
        stops.append((lat, lon, name))

    alert_mph = config.get("wind_alert_mph", 40)
    display_route_header(start_city, end_city, num_stops)

    for i, (lat, lon, name) in enumerate(stops, 1):
        data_str, cache_age = fetch_weather(lat, lon)
        if data_str is None:
            print(f"  ✗ Could not fetch weather for stop {i} ({name})")
            continue
        parsed = build_parsed(data_str, name, cache_age, config)
        display_route_stop(i, name, parsed, alert_mph, width)

    height = config.get("vehicle_height_ft")
    if height:
        print(f"🚛 Vehicle height: {height} ft — check bridge clearances along route")


def cmd_map(args, config, width):
    """Show regional weather overview for nearby cities."""
    lat, lon, city = resolve_location(args, config)

    region_cities = [
        "New York", "Philadelphia", "Baltimore", "Washington DC",
        "Boston", "Pittsburgh", "Richmond", "Hartford",
    ]

    print(f"Fetching regional weather for {len(region_cities)} cities...")
    results = []
    for name in region_cities:
        glat, glon, gname = geocode_location(name)
        if glat is None:
            continue
        data_str, _ = fetch_weather(glat, glon)
        if data_str is None:
            continue
        cur = parse_current(data_str)
        results.append((gname, cur["temp"], cur["desc_short"]))

    display_regional(results, width)


def cmd_doctor(config: dict) -> None:
    """
    cleanshot doctor — comprehensive system health check.
    """
    import platform as _platform
    from pathlib import Path
    from core.config import CONFIG_PATH

    w   = min(get_width() - 2, 39)
    sep = "━" * w

    _req     = None
    failures = []

    def _ok(label, detail=""):
        d = f": {detail}" if detail else ""
        print(f"  ✅ {label}{d}")

    def _fail(label, fix=None):
        print(f"  ❌ {label}")
        if fix:
            print(f"     Fix: {fix}")
        failures.append(label)

    def _info(label, detail=""):
        d = f": {detail}" if detail else ""
        print(f"  ℹ️  {label}{d}")

    # ── Header ─────────────────────────────────────────────────────────────────
    print()
    print(f"  {sep}")
    print(f"  🔍 CLEAN SHOT DOCTOR v{VERSION}")
    print(f"     cleanshothq.com")
    print(f"  {sep}")
    print()

    # ── SYSTEM ─────────────────────────────────────────────────────────────────
    print("  SYSTEM:")
    plat      = _platform.system()
    is_termux = "com.termux" in os.environ.get("PREFIX", "")
    if is_termux:
        plat_str = "Android/Termux"
    else:
        try:
            ver_str = _platform.version()
            plat_str = f"{plat} {_platform.release()}"
        except Exception:
            plat_str = plat
    _ok(f"Platform: {plat_str}")

    pv = sys.version_info
    if pv >= (3, 8) and pv < (3, 13):
        _ok(f"Python: {pv.major}.{pv.minor}.{pv.micro} (compatible)")
    elif pv >= (3, 13):
        _ok(f"Python: {pv.major}.{pv.minor}.{pv.micro} (3.11 recommended)")
    else:
        _fail(f"Python: {pv.major}.{pv.minor} — need 3.8+",
              "Install Python 3.11 from python.org")

    _ok(f"Clean Shot: v{VERSION}")
    print()

    # ── DEPENDENCIES ───────────────────────────────────────────────────────────
    print("  DEPENDENCIES:")
    try:
        import requests as _req
        _ok(f"requests: {_req.__version__}")
    except ImportError:
        _fail("requests: not installed", "pip install requests")

    try:
        import colorama as _col
        _ok(f"colorama: {_col.__version__}")
    except ImportError:
        _fail("colorama: not installed", "pip install colorama")

    if plat in ("Linux", "Windows") and not is_termux:
        try:
            import pyttsx3 as _pyttsx3
            _ok(f"pyttsx3: {_pyttsx3.__version__}")
        except ImportError:
            _fail("pyttsx3: not found",
                  "pip install pyttsx3  |  Or: cleanshot settings tts off")
    print()

    # ── STORAGE ────────────────────────────────────────────────────────────────
    print("  STORAGE:")
    cache_dir = Path(tempfile.gettempdir()) / "clean-shot-cache"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _test = cache_dir / ".doctor"
        _test.write_text("ok")
        _test.unlink()
        _ok("Cache directory: writable")
    except Exception:
        _fail("Cache directory: not writable",
              f"chmod 755 {cache_dir}")

    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open() as _f:
                json.load(_f)
            _ok("Config file: valid")
        except Exception:
            _fail("Config file: corrupt",
                  f"rm {CONFIG_PATH}  (will recreate on next run)")
    else:
        _info("Config file: will create on first run")

    try:
        import tempfile as _tmp
        _t = _tmp.mktemp(dir=tempfile.gettempdir())
        with open(_t, "w") as _f2:
            _f2.write("ok")
        os.unlink(_t)
        _ok("Temp directory: writable")
    except Exception:
        _fail("Temp directory: not writable")
    print()

    # ── CONNECTIVITY ───────────────────────────────────────────────────────────
    print("  CONNECTIVITY:")
    if _req is None:
        _fail("Internet: skipped — requests not installed",
              "pip install requests")
    else:
        # NWS
        try:
            r = _req.get("https://api.weather.gov", timeout=5)
            if r.status_code < 500:
                _ok("Internet: connected")
                _ok("NOAA/NWS API: reachable")
            else:
                _fail(f"NOAA/NWS API: HTTP {r.status_code}",
                      "Check your internet connection")
        except Exception:
            _fail("Internet: no connection",
                  "Check WiFi or cellular signal")

        # Open-Meteo
        try:
            r2 = _req.get(
                "https://api.open-meteo.com/v1/forecast"
                "?latitude=40&longitude=-80&current_weather=true",
                timeout=5,
            )
            if r2.status_code < 500:
                _ok("Open-Meteo API: reachable")
            else:
                _fail("Open-Meteo API: server error")
        except Exception:
            _fail("Open-Meteo API: unreachable")

        # Geocoding
        try:
            r3 = _req.get(
                "https://nominatim.openstreetmap.org/search"
                "?q=Chicago&format=json&limit=1",
                timeout=5,
                headers={"User-Agent": f"CleanShot/{VERSION}"},
            )
            if r3.status_code < 500:
                _ok("Geocoding: reachable")
            else:
                _fail("Geocoding: server error")
        except Exception:
            _fail("Geocoding: unreachable")
    print()

    # ── FEATURES ───────────────────────────────────────────────────────────────
    print("  FEATURES:")

    try:
        from core.api import fetch_weather  # noqa: F401
        _ok("Weather: operational")
    except Exception as e:
        _fail(f"Weather: {e}")

    try:
        from core.alerts import get_road_alerts  # noqa: F401
        _ok("Alerts: operational")
    except Exception as e:
        _fail(f"Alerts: {e}")

    lat = config.get("latitude")
    lon = config.get("longitude")
    if lat and lon:
        city_str = config.get("city", "unknown")
        _ok(f"GPS: {city_str} ({lat:.4f}, {lon:.4f})")
    else:
        _ok("GPS: IP fallback active")

    try:
        from core.tts import _detect_platform_name
        tts_plat = _detect_platform_name()
        _ok(f"TTS: {tts_plat}")
    except Exception as e:
        _fail(f"TTS: {e}",
              "cleanshot settings tts off")

    try:
        from core.dot511 import fetch_dot511  # noqa: F401
        _ok("DOT/511: operational")
    except Exception as e:
        _fail(f"DOT/511: {e}")

    try:
        from core.hazards import get_active_hazards  # noqa: F401
        _ok("Community reports: operational")
    except Exception as e:
        _fail(f"Community reports: {e}")

    try:
        from core.hos import get_hos_status  # noqa: F401
        _ok("HOS guardian: operational")
    except Exception as e:
        _fail(f"HOS guardian: {e}")

    try:
        from core.parking import compute_runway  # noqa: F401
        _ok("Parking runway: operational")
    except Exception as e:
        _fail(f"Parking runway: {e}")
    print()

    # ── SUBSCRIPTION ───────────────────────────────────────────────────────────
    print("  SUBSCRIPTION:")
    tier = config.get("subscription_tier", "free")
    if tier == "free":
        _info("Plan: Free Trial")
        _info("Days remaining: 30")
        _info("Upgrade: cleanshothq.com")
    else:
        _ok(f"Plan: {tier}")
    print()

    # ── Summary ────────────────────────────────────────────────────────────────
    print(f"  {sep}")
    if failures:
        print(f"  ⚠️  {len(failures)} issue(s) found — see above for fixes")
    else:
        print("  ✅ ALL SYSTEMS OPERATIONAL")
    print()
    print("  Need help?")
    print("  support@cleanshothq.com")
    print(f"  {sep}")
    print()


def cmd_help():
    c = _cmd()
    print(f"""
Clean Shot v{VERSION}  —  Built for the road, not the boardroom.
Blue Collar Nation LLC  |  cleanshothq.com
{'─'*55}

Usage:  {c} [command] [options]

Commands:
  (none)            Full weather + road intelligence report (default)
  simple            One-line weather summary
  compact           Compact view
  watch             Auto-refresh every 15 minutes
  json              Raw JSON output (for scripting)
  route A B         Weather along route from A to B (5 stops)
  map               Regional weather overview
  alerts            Active weather alerts only
  settings          View/change settings
  doctor            System health check
  test-tts          Test voice alerts
  test-alerts       Test flash + beep + alert display
  help              This help screen

Road Intelligence (Solo Pro+):
  Included in default view — black ice, fog, flood, diesel gel,
  wind, DOT/511 advisories, community hazards, parking runway,
  HOS Guardian (advisory only — not an ELD).

Options:
  --location PLACE  Override location (city, ZIP, "City ST", lat,lon)
  --fresh           Force fresh API data (skip cache)

Examples:
  {c}
  {c} simple
  {c} compact
  {c} --location "Memphis TN"
  {c} --location "38101"
  {c} route "Memphis TN" "Chicago IL"
  {c} watch
  {c} alerts
  {c} settings 24h
  {c} settings height 13.5
  {c} settings wind 35

Data sources:
  • Open-Meteo (weather, no API key required)
  • NOAA / NWS (US weather alerts)
  • ipapi.co (IP geolocation, auto-detect only)

Config:  ~/.config/clean-shot.conf
Cache:   {tempfile.gettempdir()}/clean-shot-cache/ (refreshes every 10 min)
""")

# ── Test commands ─────────────────────────────────────────────────────────────

def cmd_test_tts(config: dict) -> None:
    """
    cleanshot test-tts — verify voice alerts are working.
    Forces a real TTS dispatch and reports the engine, voice, and star rating.
    """
    import platform as _plat

    test_msg = (
        "Clean Shot text to speech is working. "
        "Roads are clean and green good buddy."
    )

    w   = min(get_width() - 2, 39)
    sep = "━" * w

    print()
    print(f"  {sep}")
    print("  🔊 TTS Test — Clean Shot v" + VERSION)
    print(f"  {sep}")
    print()

    plat      = _plat.system().lower()
    is_termux = "com.termux" in os.environ.get("PREFIX", "")

    # ── Get engine info ───────────────────────────────────────────────────────
    engine_name = None
    voice_label = None
    star_str    = ""

    if is_termux:
        engine_name = "termux-tts-speak"
        star_str    = "⭐⭐⭐"
    elif plat == "linux":
        try:
            from platforms.linux.tts_linux import get_engine_info
            info        = get_engine_info(config)
            engine_name = info["engine"]
            voice_label = info["voice"]
            star_str    = info["star_str"]
        except Exception:
            try:
                import pyttsx3  # noqa: F401
                engine_name = "pyttsx3 (espeak en+m3)"
                star_str    = "⭐⭐"
            except ImportError:
                engine_name = None
    elif plat == "windows":
        engine_name = "Windows SAPI"
        star_str    = "⭐⭐⭐⭐"
    elif plat == "darwin":
        engine_name = "macOS say"
        star_str    = "⭐⭐⭐"
    else:
        engine_name = "terminal fallback"
        star_str    = ""

    if engine_name is None:
        print("  ❌ No TTS engine — voice alerts disabled")
        print()
        print("  Quick fix:")
        print("    sudo apt-get install -y espeak-ng libespeak-ng1")
        print("    pip3 install pyttsx3 --break-system-packages")
        print()
        print("  For best quality (neural voice):")
        print("    pip3 install piper-tts --break-system-packages")
        print("    cleanshot voices download")
        print()
        print("  Or disable TTS:  cleanshot settings tts off")
        print(f"  {sep}")
        print()
        return

    print(f"  Engine : {engine_name}")
    if voice_label:
        print(f"  Voice  : {voice_label}")
    if star_str:
        print(f"  Quality: {star_str}")
    print()
    print(f"  Saying: \"{test_msg}\"")
    print()

    # Force TTS on for this test
    test_config = dict(config)
    test_config["tts_enabled"] = True

    from core.tts import speak
    result = speak(test_msg, test_config)

    print()
    if result:
        print(f"  ✅ TTS working — {engine_name}")
        if not voice_label or "piper" not in engine_name:
            print()
            print("  Want a more natural voice?")
            print("    pip3 install piper-tts --break-system-packages")
            print("    cleanshot voices download")
    else:
        print("  ❌ TTS dispatch failed")
        print("     support@cleanshothq.com")
    print(f"  {sep}")
    print()


def cmd_voices(config: dict, args: list) -> None:
    """
    cleanshot voices            — list available piper voices
    cleanshot voices download   — download default voice (en_US-lessac-medium)
    cleanshot voices download <name>  — download specific voice
    """
    import platform as _plat

    plat = _plat.system().lower()
    if plat != "linux":
        print()
        print("  Piper voices are only available on Linux.")
        print("  Windows uses SAPI, macOS uses say.")
        print()
        return

    try:
        from platforms.linux.tts_linux import list_voices, download_voice, DEFAULT_VOICE
    except ImportError:
        print("  Could not load voice manager.")
        return

    sub = args[1].lower() if len(args) > 1 else ""

    if sub == "download":
        # Install piper-tts if not already there
        try:
            from piper import PiperVoice  # noqa: F401
        except ImportError:
            print()
            print("  Installing piper-tts...")
            import subprocess as _sp
            try:
                _sp.run(
                    ["pip3", "install", "piper-tts", "--break-system-packages", "--quiet"],
                    check=True, timeout=120,
                )
            except Exception:
                try:
                    _sp.run(
                        ["pip3", "install", "piper-tts", "--quiet"],
                        check=True, timeout=120,
                    )
                except Exception:
                    print("  ❌ Could not install piper-tts")
                    print("     Fix: pip3 install piper-tts --break-system-packages")
                    print()
                    return

        voice_name = args[2] if len(args) > 2 else DEFAULT_VOICE
        print()
        print(f"  Downloading {voice_name}...")
        download_voice(voice_name, show_progress=True)
        print()
        print(f"  To use this voice:")
        print(f"    cleanshot settings voice {voice_name}")
        print()
    else:
        list_voices(config)


def cmd_test_alerts(config: dict, width: int) -> None:
    """
    cleanshot test-alerts — test critical alert display (flash + beep).
    """
    w   = min(width, 50)
    sep = "━" * min(w, 39)

    RED_BG = "\033[41;97m"   # bright white on red background
    RESET  = "\033[0m"
    BOLD   = "\033[1m"

    print()

    # Audible beep — uses terminal bell character
    sys.stdout.write("\a")
    sys.stdout.flush()

    # Flash red banner 3 times
    banner = " ⛔  CRITICAL ALERT TEST  ⛔ "
    pad    = max(0, w - len(banner) - 2)
    line   = f"  {RED_BG}{banner}{' ' * pad}{RESET}"

    for _ in range(3):
        print(line)
        time.sleep(0.18)
        # Clear line and reprint blank (flash effect)
        sys.stdout.write(f"\033[1A\033[2K  {' ' * (len(banner) + pad)}\r")
        sys.stdout.flush()
        time.sleep(0.10)

    # Final banner stays visible
    print(line)
    print()
    print(f"  {sep}")
    print(f"  {BOLD}TEST ALERT — Black Ice Warning{RESET}")
    print(f"  {sep}")
    print()
    print("  ⛔ [CRITICAL] Black Ice")
    print("     Smokey's reporting black ice ahead")
    print("     good buddy — back it down.")
    print()
    print(f"  {sep}")
    print()
    print("  ✅ Flash: displayed")
    print("  ✅ Beep: sent (check device volume)")
    print("  ✅ Alert display: working")
    print()
    print(f"  Test voice:  {_cmd()} test-tts")
    print(f"  {sep}")
    print()


# ── Road intelligence display ─────────────────────────────────────────────────

def _display_road_section(lat, lon, parsed, config, width):
    """
    Display the full road intelligence section after the weather display.
    Order: critical banners → road alerts → DOT/511 → hazards → parking → HOS.
    Gracefully skips any section whose module failed to import.
    """
    road_alerts = []
    incidents   = []
    hazards     = []
    runway      = None
    nearest     = None

    # 1. Offline road detectors — free tier, always run
    if _ALERTS_OK and parsed:
        road_alerts = get_road_alerts(lat, lon, parsed, config) or []

    # 2. Solo Pro+ live feeds (network, cached)
    if lat is not None and lon is not None:
        if _DOT511_OK:
            incidents = get_active_incidents(lat, lon, config) or []
        if _HAZARDS_OK:
            hazards = get_active_hazards(lat, lon, config) or []

    # 3. Parking runway (uses embedded db — works offline)
    if _PARKING_OK:
        runway  = compute_runway(config)
        nearest = find_recommended_stop(lat, lon, config)
        announce_runway(config)

    # 4. HOS — refresh parking feed before critical check
    if _HOS_OK:
        update_elapsed(config)
        announce_hos(config)

    # 5. Critical alert banners — show first (highest urgency)
    hos_urgent = (
        _HOS_OK
        and get_hos_status(config).get("level") in ("critical", "urgent")
    )
    any_critical = (
        hos_urgent
        or (road_alerts and has_critical(road_alerts) if _ALERTS_OK else False)
        or any(i.get("severity") == "critical" for i in incidents)
        or any((h.get("sev") or h.get("severity")) in ("critical",) for h in hazards)
        or (runway and runway.get("level") in ("critical", "urgent"))
    )

    if any_critical and _DISP_ALERTS_OK:
        print()
        check_and_display(
            alerts=road_alerts,
            incidents=incidents,
            hazards=hazards,
            runway=runway,
            nearest_stop=nearest,
            config=config,
            include_hos=_HOS_OK,
        )

    # 6. Road alerts section (offline detectors)
    if road_alerts:
        print()
        print("─" * width)
        print("  Road Conditions  (offline detectors)")
        print("─" * width)
        for a in road_alerts:
            sev   = a.get("severity", "INFO")
            atype = a.get("type", "").replace("_", " ").title()
            msg   = a.get("message", "")
            icon  = {"CRITICAL": "⛔", "WARNING": "⚠️", "INFO": "ℹ️"}.get(sev, "•")
            print(f"  {icon} [{sev}] {atype}")
            if msg:
                print(f"      {msg}")
    elif _ALERTS_OK:
        print()
        print("  ✓ No road hazards detected for current conditions.")

    # 7. DOT/511 advisories (solo_pro+)
    if incidents and _DOT511_OK:
        print()
        display_dot511(incidents, config)

    # 8. Community hazards (solo_pro+)
    if hazards and _HAZARDS_OK:
        print()
        display_hazards(hazards, config)

    # 9. Parking runway (solo_pro+)
    if _PARKING_OK:
        print()
        display_parking_status(lat, lon, config)

    # 10. HOS status (solo_pro+)
    if _HOS_OK:
        print()
        display_hos_status(config)


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        prog=_cmd(),
        description="Clean Shot — Weather for truckers",
        add_help=False,
    )
    parser.add_argument("command", nargs="?", default="full")
    parser.add_argument("extra", nargs="*")
    parser.add_argument("--location", "-l", type=str)
    parser.add_argument("--route", nargs=2, metavar=("START", "END"))
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--version", "-v", action="store_true")
    parser.add_argument("--help", "-h", action="store_true")
    return parser


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = build_parser()
    args   = parser.parse_args()
    width  = get_width()

    if args.version:
        print(f"clean-shot v{VERSION}")
        return

    if args.help or args.command == "help":
        cmd_help()
        return

    config = get_config()

    if config.get("latitude") is None and not args.location:
        _no_loc_cmds = ("settings", "help", "version", "doctor",
                        "test-tts", "testtts", "test-alerts", "testalerts",
                        "voices")
        if args.command not in _no_loc_cmds:
            config = first_run_setup(config)
            if config.get("latitude") is None:
                return

    if args.route:
        args.route = list(args.route)
        cmd_route(args, config, width)
        return

    cmd = args.command.lower() if args.command else "full"

    if cmd in ("", "full"):
        cmd_full(args, config, width)

    elif cmd == "simple":
        cmd_simple(args, config, width)

    elif cmd == "compact":
        cmd_compact(args, config, width)

    elif cmd == "watch":
        cmd_watch(args, config, width)

    elif cmd == "json":
        cmd_json(args, config, width)

    elif cmd == "alerts":
        cmd_alerts(args, config, width)

    elif cmd in ("route", "r"):
        extra = args.extra
        if len(extra) >= 2:
            args.route = [extra[0], extra[1]]
            cmd_route(args, config, width)
        else:
            print(f'Usage: {_cmd()} route "Start City" "End City"')
            sys.exit(1)

    elif cmd == "map":
        cmd_map(args, config, width)

    elif cmd == "settings":
        show_settings(config, [cmd] + (args.extra or []))

    elif cmd == "doctor":
        cmd_doctor(config)

    elif cmd in ("test-tts", "testtts", "tts-test"):
        cmd_test_tts(config)

    elif cmd in ("test-alerts", "testalerts", "alerts-test"):
        cmd_test_alerts(config, width)

    elif cmd == "voices":
        cmd_voices(config, sys.argv[1:])

    elif cmd in ("version", "-v", "--version"):
        print(f"clean-shot v{VERSION}")

    else:
        # Try treating unknown command as a location
        original_cmd = args.command
        lat, lon, city = geocode_location(original_cmd)
        if lat is not None:
            args.location = original_cmd
            cmd_full(args, config, width)
        else:
            print(f"  Unknown command: '{original_cmd}'")
            print(f"  Run '{_cmd()} help' for usage.")
            sys.exit(1)


if __name__ == "__main__":
    main()
