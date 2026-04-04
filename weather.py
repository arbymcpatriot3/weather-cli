#!/usr/bin/env python3
# weather.py - Weather CLI for Truckers
# Combines best features from all previous versions
# v2.0.0

import argparse
import sys
import os
import time
import json
from datetime import datetime

from config import get_config, save_config, first_run_setup, show_settings, VERSION
from api import fetch_weather, fetch_alerts, geocode_location, get_auto_location
from parse import parse_current, parse_forecast, parse_hourly
from display import (
    get_width, print_header,
    display_simple, display_compact, display_current,
    display_alerts, display_wind_alert,
    display_hourly, display_forecast, display_rain_timeline,
    display_regional, display_route_header, display_route_stop,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def resolve_location(args, config):
    """
    Determine lat/lon/city from args or config.
    Priority: --location arg > config saved > IP auto-detect
    Returns (lat, lon, city) or exits on failure.
    """
    if args.location:
        loc_str = args.location.strip()
        lat, lon, city = geocode_location(loc_str)
        if lat is None:
            print(f"✗ Could not find location: '{loc_str}'")
            print("  Try: --location \"Pennsville NJ\" or --location \"08079\"")
            sys.exit(1)
        # Save for future runs
        config["latitude"]  = lat
        config["longitude"] = lon
        config["city"]      = city
        save_config(config)
        return lat, lon, city

    lat = config.get("latitude")
    lon = config.get("longitude")
    city = config.get("city", "Unknown")

    if lat is not None and lon is not None:
        return lat, lon, city

    # Try IP auto-detect
    print("ℹ  Auto-detecting location via IP...")
    lat, lon, city = get_auto_location()
    if lat is not None:
        print(f"✓  Detected: {city}")
        config["latitude"]  = lat
        config["longitude"] = lon
        config["city"]      = city
        save_config(config)
        return lat, lon, city

    print("✗ No location configured. Please run: weather settings location")
    sys.exit(1)


def build_parsed(data_str, city, cache_age, config):
    """Build the unified parsed data dict used by display functions."""
    return {
        "current":      parse_current(data_str),
        "forecast":     parse_forecast(data_str),
        "hourly":       parse_hourly(data_str),
        "city":         city,
        "timestamp":    datetime.now().strftime("%m/%d/%Y %I:%M %p"),
        "time_format":  config.get("time_format", "12h"),
        "cache_age":    cache_age or 0,
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

    parsed   = build_parsed(data_str, city, cache_age, config)
    alerts   = fetch_alerts(lat, lon)
    alert_mph = config.get("wind_alert_mph", 40)

    print_header(f"Weather for {city}", width, VERSION)
    display_current(parsed, width)
    display_alerts(alerts, width)
    display_wind_alert(parsed["hourly"], alert_mph, width)
    display_hourly(parsed["hourly"], width, parsed["time_format"], alert_mph)
    display_forecast(parsed["forecast"], width)
    display_rain_timeline(parsed["hourly"], width, parsed["time_format"])


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
        from display import display_alerts
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
                print_header(f"Weather for {city}  [Auto-refresh every 15 min]",
                             width, VERSION)
                display_current(parsed, width)
                display_alerts(alerts, width)
                display_wind_alert(parsed["hourly"], alert_mph, width)
                display_hourly(parsed["hourly"], width,
                               parsed["time_format"], alert_mph)
                display_forecast(parsed["forecast"], width)
            else:
                print("⚠  Failed to fetch update. Retrying in 15 min...")
            print(f"\n  Last updated: {datetime.now().strftime('%H:%M:%S')} "
                  f"| Ctrl+C to exit")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n  Exiting watch mode.")


def cmd_route(args, config, width):
    """Show weather along a route with configurable stops."""
    if not args.route or len(args.route) < 2:
        print("Usage: weather route \"Start City\" \"End City\"")
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

    # Generate evenly spaced stops
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

    # Show vehicle height reminder
    height = config.get("vehicle_height_ft")
    if height:
        print(f"🚛 Vehicle height: {height} ft  — check bridge clearances along route")


def cmd_map(args, config, width):
    """Show regional weather overview for nearby cities."""
    lat, lon, city = resolve_location(args, config)

    # Fixed regional cities (could be config-driven in future)
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


def cmd_help():
    print(f"""
Weather CLI v{VERSION}  —  Designed for truckers & travelers
{'─'*55}

Usage:  weather [command] [options]

Commands:
  (none)            Full weather report (default)
  simple            One-line summary
  compact           80-column compact view
  watch             Auto-refresh every 15 minutes
  json              Raw JSON output (for scripting)
  route A B         Weather along route from A to B (5 stops)
  map               Regional weather overview
  alerts            Active weather alerts only
  settings          View/change settings
  help              This help screen

Options:
  --location PLACE  Override location (city, ZIP, "City ST", lat,lon)
  --fresh           Force fresh API data (skip cache)

Examples:
  weather
  weather simple
  weather compact
  weather --location "Chicago IL"
  weather --location "08079"
  weather route "Pennsville NJ" "Chicago IL"
  weather watch
  weather alerts
  weather settings 24h
  weather settings height 13.5
  weather settings wind 35

Data sources:
  • Open-Meteo (weather, no API key required)
  • NOAA / NWS (US weather alerts)
  • ipapi.co (IP geolocation, auto-detect only)

Config: ~/.config/weather-cli.conf
Cache:  /tmp/weather-cli-cache/ (refreshes every 10 min)
""")


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        prog="weather",
        description="Weather CLI for Truckers",
        add_help=False,
    )
    parser.add_argument("command", nargs="?", default="full",
                        help="Command to run")
    parser.add_argument("extra", nargs="*",
                        help="Extra args for settings/route")
    parser.add_argument("--location", "-l", type=str,
                        help="Location override")
    parser.add_argument("--route", nargs=2, metavar=("START", "END"),
                        help="Route start and end")
    parser.add_argument("--fresh", action="store_true",
                        help="Force fresh API call")
    parser.add_argument("--version", "-v", action="store_true",
                        help="Show version")
    parser.add_argument("--help", "-h", action="store_true",
                        help="Show help")
    return parser


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser  = build_parser()
    args    = parser.parse_args()
    width   = min(get_width(), 80)

    # Handle --version and --help flags immediately
    if args.version:
        print(f"weather-cli v{VERSION}")
        return

    if args.help or args.command == "help":
        cmd_help()
        return

    # Load config
    config = get_config()

    # First-run setup if no location saved
    if config.get("latitude") is None and not args.location:
        if args.command not in ("settings", "help", "version"):
            config = first_run_setup(config)
            if config.get("latitude") is None:
                return  # Setup was skipped

    # Route via --route flag
    if args.route:
        args.route = list(args.route)
        cmd_route(args, config, width)
        return

    # Command dispatch
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
        # weather route "Start" "End"
        extra = args.extra
        if len(extra) >= 2:
            args.route = [extra[0], extra[1]]
            cmd_route(args, config, width)
        else:
            print('Usage: weather route "Start City" "End City"')
            sys.exit(1)

    elif cmd == "map":
        cmd_map(args, config, width)

    elif cmd == "settings":
        show_settings(config, [cmd] + (args.extra or []))

    elif cmd in ("version", "-v", "--version"):
        print(f"weather-cli v{VERSION}")

    else:
        # Try treating unknown command as a location (preserve original case)
        original_cmd = args.command  # not lowercased
        lat, lon, city = geocode_location(original_cmd)
        if lat is not None:
            args.location = original_cmd
            cmd_full(args, config, width)
        else:
            print(f"✗ Unknown command: '{original_cmd}'")
            print("  Run 'weather help' for usage.")
            sys.exit(1)


if __name__ == "__main__":
    main()
