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
            print(f"✗ Could not find location: '{loc_str}'")
            print('  Try: --location "Memphis TN" or --location "38101"')
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

    print(f"✗ No location configured. Run: {_cmd()} settings location")
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
        loc = label or f"({lat:.4f}, {lon:.4f})"
        print(f"✗ Failed to fetch weather data for {loc}")
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
    cleanshot doctor — system health check.
    Prints status of Python, deps, cache, config, GPS, TTS, and network.
    """
    import platform as _platform
    from pathlib import Path
    from core.config import CONFIG_PATH

    ok_  = "✅"
    bad_ = "❌"
    wrn_ = "⚠️ "

    w = get_width()
    sep = "─" * min(w, 50)

    print()
    print(f"  Clean Shot v{VERSION} — Doctor")
    print(f"  {sep}")

    # Python version
    pv = sys.version_info
    py_path = sys.executable
    if pv >= (3, 8):
        print(f"  {ok_} Python {pv.major}.{pv.minor}.{pv.micro}  {py_path}")
    else:
        print(f"  {bad_} Python {pv.major}.{pv.minor} — need 3.8+  {py_path}")

    # Platform
    plat = _platform.system()
    is_termux = "com.termux" in os.environ.get("PREFIX", "")
    plat_str  = "Android/Termux" if is_termux else f"{plat} {_platform.release()}"
    print(f"  {ok_} Platform — {plat_str}")

    # requests
    try:
        import requests as _req
        print(f"  {ok_} requests installed")
    except ImportError:
        print(f"  {bad_} requests missing — run: pip install requests")
        _req = None

    # colorama
    try:
        import colorama  # noqa: F401
        print(f"  {ok_} colorama installed")
    except ImportError:
        print(f"  {wrn_} colorama missing — colors disabled  (pip install colorama)")

    # Cache dir writable
    cache_dir = Path(tempfile.gettempdir()) / "clean-shot-cache"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _test = cache_dir / ".doctor"
        _test.write_text("ok")
        _test.unlink()
        print(f"  {ok_} Cache dir writable — {cache_dir}")
    except Exception as e:
        print(f"  {bad_} Cache dir not writable — {cache_dir}: {e}")

    # Config file
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open() as _f:
                json.load(_f)
            loc = config.get("city") or "no location set"
            print(f"  {ok_} Config valid — {loc}  ({CONFIG_PATH})")
        except Exception as e:
            print(f"  {bad_} Config corrupt — {e}")
    else:
        print(f"  {wrn_} No config yet — will create on first run")

    # GPS module
    try:
        from core.gps import get_position  # noqa: F401
        print(f"  {ok_} GPS module available")
    except ImportError as e:
        print(f"  {bad_} GPS module error — {e}")

    # TTS
    try:
        from core.tts import _detect_platform_name
        tts_plat = _detect_platform_name()
        print(f"  {ok_} TTS available — {tts_plat}")
    except Exception as e:
        print(f"  {bad_} TTS error — {e}")

    # Network
    if _req is not None:
        try:
            r = _req.get("https://api.weather.gov", timeout=5)
            if r.status_code < 500:
                print(f"  {ok_} Network — NWS reachable (HTTP {r.status_code})")
            else:
                print(f"  {wrn_} Network — NWS returned HTTP {r.status_code}")
        except Exception as e:
            print(f"  {bad_} Network — {e}")
    else:
        print(f"  {bad_} Network — skipped (requests not installed)")

    # Location
    lat = config.get("latitude")
    lon = config.get("longitude")
    if lat and lon:
        city = config.get("city", "unknown")
        print(f"  {ok_} Location — {city} ({lat:.4f}, {lon:.4f})")
    else:
        print(f"  {wrn_} No location set — run: {_cmd()} settings location")

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
        if args.command not in ("settings", "help", "version"):
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
            print(f"✗ Unknown command: '{original_cmd}'")
            print(f"  Run '{_cmd()} help' for usage.")
            sys.exit(1)


if __name__ == "__main__":
    main()
