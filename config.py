#!/usr/bin/env python3
# config.py - Configuration management for Weather CLI

from pathlib import Path
import json
import sys

CONFIG_PATH = Path.home() / ".config" / "weather-cli.conf"
VERSION = "2.0.0"


def get_config():
    """Load config, creating defaults if missing."""
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open() as f:
                config = json.load(f)
            # Ensure all defaults exist
            config.setdefault("time_format", "12h")
            config.setdefault("units", "imperial")
            config.setdefault("vehicle_height_ft", None)
            config.setdefault("wind_alert_mph", 40)
            return config
        except Exception:
            pass
    # Default config
    config = {
        "time_format": "12h",
        "units": "imperial",
        "vehicle_height_ft": None,
        "wind_alert_mph": 40,
    }
    save_config(config)
    return config


def save_config(config):
    """Save config to disk."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w") as f:
        json.dump(config, f, indent=2)


def first_run_setup(config):
    """Interactive first-run setup wizard."""
    print("=" * 50)
    print("  Weather CLI - First Run Setup")
    print("=" * 50)
    print()
    print("No location configured. Let's set one up.")
    print("You can enter a city name, ZIP code, or city+state.")
    print('Example: "Pennsville NJ" or "08079" or "Chicago"')
    print()

    from api import geocode_location
    while True:
        try:
            loc = input("Enter your location: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSetup cancelled.")
            sys.exit(0)

        if not loc:
            print("Please enter a location.")
            continue

        lat, lon, city = geocode_location(loc)
        if lat is None:
            print(f"Could not find '{loc}'. Please try again.")
            continue

        config["latitude"] = lat
        config["longitude"] = lon
        config["city"] = city
        print(f"✓ Location set to: {city} ({lat:.4f}, {lon:.4f})")
        break

    # Ask about time format
    print()
    fmt = input("Time format: 12h or 24h? [12h]: ").strip().lower()
    config["time_format"] = "24h" if fmt == "24h" else "12h"

    # Ask about vehicle height (optional)
    print()
    print("Trucker feature: Save your vehicle height for wind alerts.")
    print("Standard semi-trailer is ~13.5 ft. Press Enter to skip.")
    try:
        h = input("Vehicle height in feet [Enter to skip]: ").strip()
        if h:
            config["vehicle_height_ft"] = float(h)
            print(f"✓ Vehicle height saved: {config['vehicle_height_ft']} ft")
    except (ValueError, EOFError, KeyboardInterrupt):
        pass

    save_config(config)
    print()
    print("Setup complete! Run 'weather' anytime for your forecast.")
    print()
    return config


def show_settings(config, args):
    """Display or update settings."""
    print("Weather CLI Settings")
    print("-" * 40)
    city = config.get("city", "Not set")
    lat  = config.get("latitude", "")
    lon  = config.get("longitude", "")
    print(f"Location     : {city}")
    if lat:
        print(f"Coordinates  : {lat:.4f}, {lon:.4f}")
    print(f"Time format  : {config.get('time_format', '12h')}")
    height = config.get("vehicle_height_ft")
    print(f"Vehicle height: {height} ft" if height else "Vehicle height: Not set")
    print(f"Wind alert   : {config.get('wind_alert_mph', 40)} mph")
    print()
    print("To change settings, use:")
    print("  weather settings 12h          Set 12-hour time")
    print("  weather settings 24h          Set 24-hour time")
    print("  weather settings height 13.5  Set vehicle height")
    print("  weather settings wind 35      Set wind alert threshold")
    print("  weather settings location     Change default location")
    print()

    # Handle sub-commands
    if len(args) >= 2:
        key = args[1].lower()
        if key in ("12h", "24h"):
            config["time_format"] = key
            save_config(config)
            print(f"✓ Time format set to {key}")
        elif key == "height" and len(args) >= 3:
            try:
                config["vehicle_height_ft"] = float(args[2])
                save_config(config)
                print(f"✓ Vehicle height set to {args[2]} ft")
            except ValueError:
                print("Invalid height value.")
        elif key == "wind" and len(args) >= 3:
            try:
                config["wind_alert_mph"] = float(args[2])
                save_config(config)
                print(f"✓ Wind alert threshold set to {args[2]} mph")
            except ValueError:
                print("Invalid wind speed value.")
        elif key == "location":
            from api import geocode_location
            try:
                loc = input("Enter new location: ").strip()
                lat, lon, city = geocode_location(loc)
                if lat:
                    config["latitude"] = lat
                    config["longitude"] = lon
                    config["city"] = city
                    save_config(config)
                    print(f"✓ Location updated to: {city}")
                else:
                    print(f"Could not find '{loc}'.")
            except (EOFError, KeyboardInterrupt):
                print("\nCancelled.")
        else:
            print(f"Unknown setting: {key}")
