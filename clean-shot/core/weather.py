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

try:
    from core.road511 import check_route_safety, fetch_bridges, fetch_weigh_stations
    from display.full import display_route_safety, display_bridge_alerts, display_weigh_stations
    _ROAD511_OK = True
except ImportError:
    _ROAD511_OK = False


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
        # On Android: refresh location through fallback chain before using cached coords
        if os.environ.get("TERMUX_VERSION") or "com.termux" in os.environ.get("PREFIX", ""):
            # 1. termux-location (F-Droid Termux only — not available on Google Play)
            try:
                from core.gps import _get_termux_location
                gps = _get_termux_location()
                if gps and not gps.get("stale"):
                    lat = gps["lat"]
                    lon = gps["lon"]
                    config["latitude"]  = lat
                    config["longitude"] = lon
                    print(f"  📍 {city}  GPS ✅")
                    return lat, lon, city
            except Exception:
                pass

            # 2. IP geolocation (always available, less precise)
            try:
                ip_lat, ip_lon, ip_city = get_auto_location()
                if ip_lat is not None:
                    lat, lon = ip_lat, ip_lon
                    if ip_city:
                        city = ip_city
                        config["city"] = city
                    config["latitude"]  = lat
                    config["longitude"] = lon
                    print(f"  📍 {city}")
                    print(f"     Source: IP geolocation ⚠️")
                    print(f"     For GPS accuracy: install Termux from F-Droid")
                    return lat, lon, city
            except Exception:
                pass

            # 3. Cached config coords — last resort
            print(f"  📍 {city}  Cached ⚠️")
            print(f"     Run: {_cmd()} update-location")

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


def cmd_road_safety(args, config, width):
    """cleanshot route (no dest) — full Road511 safety check at current location."""
    if not _ROAD511_OK:
        print("  Road511 module not available.")
        return

    lat, lon, city = resolve_location(args, config)
    print(f"  Checking route safety near {city}...")
    report = check_route_safety(lat, lon, config)
    display_route_safety(report, config, width)

    if config.get("tts_enabled") and report.get("bridge_alerts"):
        try:
            from core.tts import speak_alert
            for b in report["bridge_alerts"][:2]:
                speak_alert("bridge_clearance", "CRITICAL", config, force=True)
        except Exception:
            pass


def cmd_truck_routing(dest_str: str, args, config, width):
    """cleanshot route <dest> — truck-safe routing to destination."""
    if not _ROAD511_OK:
        print("  Road511 module not available.")
        return

    lat, lon, city = resolve_location(args, config)

    from core.api import geocode_location
    dest_lat, dest_lon, dest_city = geocode_location(dest_str)
    if dest_lat is None:
        print(f"  Can't find destination: '{dest_str}'")
        sys.exit(1)

    config["last_route_origin"] = f"{lat:.4f},{lon:.4f}"
    config["last_route_dest"]   = f"{dest_lat:.4f},{dest_lon:.4f}"
    save_config(config)

    print(f"  Checking truck routing: {city} → {dest_city}...")

    from core.road511 import fetch_truck_routing
    routing = fetch_truck_routing(
        {"lat": lat, "lon": lon},
        {"lat": dest_lat, "lon": dest_lon},
        config,
    )

    print()
    safe_icon = "✅" if routing.get("safe") else "🚨"
    print(f"  {safe_icon} Truck Route: {city} → {dest_city}")
    dist  = routing.get("distance_miles", 0)
    dur   = routing.get("duration_min", 0)
    staa  = " (STAA route)" if routing.get("staa_route") else ""
    print(f"  Distance: {dist:.0f} mi  |  Est. drive: {dur:.0f} min{staa}")
    print()

    warnings = routing.get("warnings", [])
    if warnings:
        print("  Warnings:")
        for w in warnings[:5]:
            print(f"    ⚠  {w}")
        print()

    report = check_route_safety(lat, lon, config)
    display_route_safety(report, config, width)


def cmd_bridges(args, config, width):
    """cleanshot bridges — bridge clearances within 50 miles."""
    if not _ROAD511_OK:
        print("  Road511 module not available.")
        return
    if not config.get("road511_api_key"):
        print("  Road511 API key not set.")
        print(f"  Run: {_cmd()} settings road511-key <key>")
        return

    lat, lon, city = resolve_location(args, config)
    height = config.get("vehicle_height_ft", 13.5) or 13.5

    print(f"  Fetching bridge clearances near {city}...")
    bridges = fetch_bridges(lat, lon, config)
    display_bridge_alerts(bridges, height, width)


def cmd_weigh(args, config, width):
    """cleanshot weigh — weigh station status in the next 50 miles."""
    if not _ROAD511_OK:
        print("  Road511 module not available.")
        return
    if not config.get("road511_api_key"):
        print("  Road511 API key not set.")
        print(f"  Run: {_cmd()} settings road511-key <key>")
        return

    lat, lon, city = resolve_location(args, config)
    print(f"  Fetching weigh station status near {city}...")
    stations = fetch_weigh_stations(lat, lon, config)
    display_weigh_stations(stations, width)


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
    print(f"     Driver Intelligence System")
    print(f"     cleanshothq.com")
    print(f"  {sep}")
    print()

    # ── SYSTEM ─────────────────────────────────────────────────────────────────
    print("  SYSTEM:")
    plat      = _platform.system()
    is_termux = (
        bool(os.environ.get("TERMUX_VERSION"))
        or "com.termux" in os.environ.get("PREFIX", "")
    )
    if is_termux:
        plat_str = "Android/Termux"
    else:
        try:
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

    _ok(f"Clean Shot: v{VERSION} — Driver Intelligence System")
    print()

    # ── ANDROID SPECIFIC ───────────────────────────────────────────────────────
    if is_termux:
        import shutil as _shutil
        print("  ANDROID:")
        _ok("Termux detected")

        # termux-api
        if _shutil.which("termux-tts-speak"):
            _ok("termux-api: installed  (TTS ready)")
        else:
            _fail("termux-api: not installed",
                  "pkg install termux-api")

        # Google Play vs F-Droid
        tv = os.environ.get("TERMUX_VERSION", "")
        if "googleplay" in tv.lower():
            _fail("Google Play Termux detected",
                  "For full GPS install from F-Droid: https://f-droid.org")
            _info("GPS limited — using IP geolocation instead")
        else:
            _ok("F-Droid Termux — full GPS available")
            if _shutil.which("termux-location"):
                _ok("termux-location: available  (GPS ready)")
            else:
                _fail("termux-location: not available",
                      "pkg install termux-api  then enable Location permission")

        # sox tones
        if _shutil.which("play"):
            _ok("sox: installed  (alert tones ready)")
        else:
            _fail("sox: not installed  (tones unavailable)",
                  "pkg install sox")
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
            _ver = getattr(_pyttsx3, "__version__", "installed")
            _ok(f"pyttsx3: {_ver}")
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
        # Primary internet check: Open-Meteo (always reachable, no geo-blocking)
        _internet_ok = False
        try:
            import urllib.request as _urlreq
            _urlreq.urlopen("https://api.open-meteo.com", timeout=5)
            _ok("Internet: connected")
            _internet_ok = True
        except Exception:
            try:
                r = _req.get("https://api.open-meteo.com", timeout=5)
                if r.status_code < 500:
                    _ok("Internet: connected")
                    _internet_ok = True
            except Exception:
                _fail("Internet: no connection",
                      "Check WiFi or cellular signal")

        # NWS — always checked (shown even when primary internet check failed)
        try:
            r = _req.get("https://api.weather.gov", timeout=5)
            if r.status_code < 500:
                _ok("NOAA/NWS API: reachable")
            else:
                _fail(f"NOAA/NWS API: HTTP {r.status_code}",
                      "US-only service — alerts may not work outside US")
        except Exception:
            _info("NOAA/NWS API: unreachable (alerts limited outside US)")

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
        # Always read from config — never trust the stale city string
        _ok(f"Location: {float(lat):.4f}, {float(lon):.4f} (from config)")
        # Sanity check: warn when last GPS differs by 500+ miles from config
        last_lat = config.get("last_gps_lat")
        last_lon = config.get("last_gps_lon")
        if last_lat and last_lon:
            try:
                from core.gps import haversine as _hv
                _dist = _hv(float(lat), float(lon),
                            float(last_lat), float(last_lon))
                if _dist > 500:
                    _fail(
                        f"Location mismatch: {_dist:.0f} mi from last GPS fix",
                        "cleanshot settings location  (to update home base)"
                    )
            except Exception:
                pass
    else:
        _ok("Location: not set — IP geolocation active")

    try:
        if is_termux:
            _ok("TTS: termux-tts-speak")
        elif plat == "Linux":
            from platforms.linux.tts_linux import get_engine_info as _gei
            _vi = _gei(config)
            _ok(f"TTS: {_vi['engine'] or 'no engine'}")
        else:
            from core.tts import _detect_platform_name
            _ok(f"TTS: {_detect_platform_name()}")
    except Exception as e:
        _fail(f"TTS: {e}", "cleanshot settings tts off")

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

    # ── VOICE ─────────────────────────────────────────────────────────────────
    import platform as _plat
    print("  VOICE:")
    _plat_name = _plat.system().lower()
    is_termux  = "com.termux" in os.environ.get("PREFIX", "")

    if is_termux:
        _ok("Engine: termux-tts-speak  ⭐⭐⭐")
    elif _plat_name == "linux":
        try:
            from platforms.linux.tts_linux import get_engine_info
            _vinfo = get_engine_info(config)
            if _vinfo["engine"]:
                if _vinfo.get("degraded", False):
                    _fail(
                        f"Engine: {_vinfo['engine']}  {_vinfo['star_str']}",
                        "cleanshot fix-voice"
                    )
                else:
                    _ok(f"Engine: {_vinfo['engine']}  {_vinfo['star_str']}")
                if _vinfo.get("voice"):
                    _ok(f"Voice: {_vinfo['voice']}")
            else:
                _fail("No TTS engine installed", "cleanshot fix-voice")
        except Exception:
            _fail("Could not detect voice engine", "cleanshot fix-voice")
    elif _plat_name == "windows":
        _ok("Engine: Windows SAPI  ⭐⭐⭐⭐")
    elif _plat_name == "darwin":
        _voice = config.get("tts_macos_voice", "Samantha")
        _ok(f"Engine: macOS say -v {_voice}  ⭐⭐⭐⭐")
    else:
        _ok("Engine: terminal fallback")

    # Tone check
    try:
        from platforms.linux.tts_tones import tones_exist, TONE_DIR
        if _plat_name == "linux":
            if tones_exist():
                _ok(f"Alert tones: generated  ({TONE_DIR})")
            else:
                _info("Alert tones: not yet generated (will auto-generate on first alert)")
    except Exception:
        pass

    print()

    # ── SUBSCRIPTION ───────────────────────────────────────────────────────────
    print("  SUBSCRIPTION:")
    import time as _time_sub, math as _math_sub
    tier = config.get("subscription_tier", "free")
    if tier == "free":
        trial_start = config.get("trial_start")
        if trial_start is not None:
            _elapsed = (_time_sub.time() - trial_start) / 86400.0
            _days_left = max(0, int(_math_sub.ceil(30 - _elapsed)))
        else:
            _days_left = 30
        _info(f"Plan: Free Trial — {_days_left} day(s) remaining")
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


def cmd_replaces(config: dict, short: bool = False) -> None:
    """cleanshot replaces — show what Clean Shot replaces and how much it saves."""
    from display.replaces import display_replaces, get_tts_summary
    display_replaces(config, short=short)
    if config.get("tts_enabled", False) and not short:
        from core.tts import speak
        speak(get_tts_summary(), config, bypass_quiet=True)


def cmd_help():
    c = _cmd()
    print(f"""
Clean Shot v{VERSION} — Driver Intelligence System
Built for the road, not the boardroom.
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
  replaces          What Clean Shot replaces and how much it saves
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
    cleanshot test-tts — full voice system demo.
    Plays INFO → WARNING → CRITICAL tones + messages, then shows repeat prompt.
    """
    import platform as _plat

    w   = min(get_width() - 2, 39)
    sep = "━" * w

    plat      = _plat.system().lower()
    from core.tts import _is_termux
    is_termux = _is_termux()

    # ── Get engine info ───────────────────────────────────────────────────────
    engine_name = None
    voice_label = None
    star_str    = ""
    degraded    = False

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
            degraded    = info.get("degraded", False)
        except Exception:
            engine_name = None
    elif plat == "windows":
        engine_name = "Windows SAPI"
        star_str    = "⭐⭐⭐⭐"
    elif plat == "darwin":
        voice = config.get("tts_macos_voice", "Samantha")
        engine_name = f"macOS say -v {voice}"
        star_str    = "⭐⭐⭐⭐"
    else:
        engine_name = "terminal fallback"
        star_str    = ""

    print()
    print(f"  {sep}")
    print("  🔊 TTS Test — Clean Shot v" + VERSION + " | Driver Intelligence System")
    print(f"  {sep}")
    print()

    if engine_name is None:
        print("  ❌ No TTS engine — voice alerts disabled")
        print()
        print("  Fix it now:  cleanshot fix-voice")
        print(f"  {sep}")
        print()
        return

    print(f"  Engine : {engine_name}")
    if voice_label:
        print(f"  Voice  : {voice_label}")
    if star_str:
        print(f"  Quality: {star_str}")
    print()

    test_config = dict(config)
    test_config["tts_enabled"]     = True
    test_config["tts_tone_enabled"] = True

    from core.tts import speak

    # ── INFO demo ─────────────────────────────────────────────────────────────
    print("  Testing INFO tone + message...")
    _play_tone_for_test("INFO", test_config)
    time.sleep(0.2)
    speak(
        "Info message test. Weigh station closed at mile marker 203.",
        test_config,
    )
    time.sleep(0.5)

    # ── WARNING demo ──────────────────────────────────────────────────────────
    print("  Testing WARNING tone + message...")
    _play_tone_for_test("WARNING", test_config)
    time.sleep(0.2)
    speak(
        "Warning message test. "
        "Construction zone ahead on Interstate 76. "
        "Single lane traffic.",
        test_config,
    )
    time.sleep(0.5)

    # ── CRITICAL demo ─────────────────────────────────────────────────────────
    print("  Testing CRITICAL tone + message...")
    _play_tone_for_test("CRITICAL", test_config)
    time.sleep(0.2)
    speak(
        "Critical alert test. "
        "Black ice reported ahead on Interstate 76 "
        "near mile marker 142. "
        "Back it down good buddy.",
        test_config,
    )
    time.sleep(0.3)

    # ── Result ────────────────────────────────────────────────────────────────
    print()
    print(f"  {sep}")
    if voice_label:
        print(f"  ✅ Voice: {voice_label} (Piper TTS)")
    else:
        print(f"  ✅ Voice: {engine_name}")
    tones_ok = _tones_available()
    print(f"  {'✅' if tones_ok else '❌'} Tones: {'generated and working' if tones_ok else 'not available'}")
    print(f"  🔁 Press R to test repeat →  cleanshot test-tts")
    print(f"  {sep}")
    print()

    if degraded:
        print("  ⚠️  Voice quality degraded — robotic voice detected")
        print("     Run: cleanshot fix-voice    to restore natural voice")
        print()


def _play_tone_for_test(severity: str, config: dict) -> None:
    """Play a tone during test-tts — suppresses all errors."""
    try:
        from core.tts import _is_termux
        if _is_termux():
            from platforms.android.tts_tones_android import play_tone_android
            play_tone_android(severity, config)
            return
        import platform as _plat
        if _plat.system().lower() == "linux":
            from platforms.linux.tts_tones import play_tone, ensure_tones
            ensure_tones(config.get("tts_tone_volume", 0.8))
            play_tone(severity, config)
    except Exception:
        pass


def _tones_available() -> bool:
    """Return True if tones are available on this platform."""
    try:
        from core.tts import _is_termux
        if _is_termux():
            from platforms.android.tts_tones_android import sox_available
            return sox_available()
        import platform as _plat
        if _plat.system().lower() == "linux":
            from platforms.linux.tts_tones import tones_exist
            return tones_exist()
    except Exception:
        pass
    return False


def cmd_fix_voice(config: dict) -> None:
    """
    cleanshot fix-voice — detect platform and restore best available voice.
    """
    import platform as _plat

    plat = _plat.system().lower()

    if plat == "linux":
        try:
            from platforms.linux.tts_linux import fix_voice
            fix_voice(show_progress=True)
        except Exception as e:
            print(f"\n  ❌ Fix failed: {e}")
            print("     support@cleanshothq.com\n")

    elif plat == "windows":
        print()
        print("  Windows uses built-in SAPI voices.")
        print("  For best quality, ensure 'David' or 'Mark' is installed:")
        print("  Settings → Time & Language → Speech → Add voices")
        print()

    elif plat == "darwin":
        voice = config.get("tts_macos_voice", "Samantha")
        print()
        print(f"  macOS using: say -v {voice}")
        print("  Available natural voices: Samantha (female), Alex (male)")
        print(f"  Change: cleanshot settings tts-macos-voice Samantha")
        print()

    else:
        print()
        print("  fix-voice is available on Linux, Windows, and macOS.")
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

    # 7. DOT/511 advisories (solo_pro+)
    if incidents and _DOT511_OK:
        print()
        display_dot511(incidents, config)

    # 8. Community hazards (solo_pro+)
    if hazards and _HAZARDS_OK:
        print()
        display_hazards(hazards, config)

    # All-clear banner — shown only when every road-intelligence source is quiet
    if not road_alerts and not incidents and not hazards:
        bar = "═" * min(width - 2, 58)
        print()
        print(f"  {bar}")
        print(f"  🟢  You've got a clean shot, good buddy!")
        print(f"      Road is clear — keep the shiny side up.")
        print(f"  {bar}")

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
    parser.add_argument("--location", "-l", type=str,
                        help="Location (city, ZIP, 'City ST', lat,lon)")
    parser.add_argument("--zip", type=str, dest="zip_code",
                        help="ZIP code shorthand for --location")
    parser.add_argument("--route", nargs=2, metavar=("START", "END"))
    parser.add_argument("--fresh", action="store_true",
                        help="Force fresh API call (skip cache)")
    parser.add_argument("--no-tts", action="store_true", dest="no_tts",
                        help="Disable text-to-speech for this run")
    parser.add_argument("--compact", action="store_true",
                        help="Run in compact display mode")
    parser.add_argument("--short", action="store_true",
                        help="Short output (used with replaces command)")
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

    # ── Apply --zip as --location shorthand ───────────────────────────────────
    if getattr(args, "zip_code", None) and not args.location:
        args.location = args.zip_code

    # ── Apply --no-tts flag ───────────────────────────────────────────────────
    if getattr(args, "no_tts", False):
        config["tts_enabled"] = False

    # ── Apply --fresh: skip cache AND reset GPS so location re-resolves ───────
    if getattr(args, "fresh", False):
        for _k in ("last_gps_lat", "last_gps_lon", "last_gps_time", "last_gps_source"):
            config[_k] = None

    # ── Apply --compact flag (override positional command) ────────────────────
    if getattr(args, "compact", False) and args.command == "full":
        args.command = "compact"

    # ── Auto-update: show pending message, launch background check ────────────
    try:
        from core.updater import check_and_update, get_pending_message
        msg = get_pending_message(config, save_config)
        if msg:
            print(msg)
            print()
        check_and_update(config, save_config)
    except Exception:
        pass   # updater never blocks or crashes the app

    if config.get("latitude") is None and not args.location:
        _no_loc_cmds = ("settings", "help", "version", "doctor",
                        "test-tts", "testtts", "test-alerts", "testalerts",
                        "voices", "fix-voice", "fixvoice")
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
        extra = args.extra or []
        if len(extra) == 0:
            cmd_road_safety(args, config, width)
        elif len(extra) == 1:
            cmd_truck_routing(extra[0], args, config, width)
        else:
            args.route = [extra[0], extra[1]]
            cmd_route(args, config, width)

    elif cmd == "bridges":
        cmd_bridges(args, config, width)

    elif cmd in ("weigh", "weigh-stations", "weighstation"):
        cmd_weigh(args, config, width)

    elif cmd == "safety":
        cmd_road_safety(args, config, width)

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

    elif cmd in ("fix-voice", "fixvoice"):
        cmd_fix_voice(config)

    elif cmd in ("replaces", "replace"):
        cmd_replaces(config, short=getattr(args, "short", False))

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
