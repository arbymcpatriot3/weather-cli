#!/usr/bin/env python3
# core/config.py — Clean Shot: configuration management
# Enhanced from weather-cli v2.0.0 config.py
# New fields: subscription_tier, driver_id, referral_code, vehicle_type,
#             home_base, tts_enabled, voice_enabled, offline_mode

from pathlib import Path
import json
import sys

CONFIG_PATH = Path.home() / ".config" / "clean-shot.conf"
VERSION     = "3.0.0"

_DEFAULTS = {
    # Location
    "latitude":          None,
    "longitude":         None,
    "city":              None,
    # Display
    "time_format":       "12h",
    "units":             "imperial",
    # Vehicle
    "vehicle_height_ft": None,
    "vehicle_type":      "semi",      # semi | box | flatbed | tanker | rv
    # Alerts
    "wind_alert_mph":    40,
    # Features
    "tts_enabled":       False,
    "voice_enabled":     False,
    "offline_mode":      False,
    # Account
    "driver_id":         None,
    "subscription_tier": "free",      # free | solo_pro | pro_plus | fleet | enterprise
    "referral_code":     None,
    "home_base":         None,
    # Referral stats (local cache — source of truth is server)
    "referral_count":    0,
    "referral_tier":     "road_scout", # road_scout → captain → commander → legend → elite → ambassador
    # GPS / location
    "language":          "en",         # en | es (auto-detected on first run)
    "last_gps_lat":      None,
    "last_gps_lon":      None,
    "last_gps_time":     None,
    "last_gps_source":   None,         # "gps" | "ip" | "config"
    "is_driving":        False,
}


# ── Load / Save ───────────────────────────────────────────────────────────────

def get_config() -> dict:
    """Load config, back-filling any missing defaults."""
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open() as f:
                config = json.load(f)
            for key, val in _DEFAULTS.items():
                config.setdefault(key, val)
            return config
        except Exception:
            pass
    config = dict(_DEFAULTS)
    save_config(config)
    return config


def save_config(config: dict):
    """Persist config to disk."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w") as f:
        json.dump(config, f, indent=2)


# ── First-run setup ───────────────────────────────────────────────────────────

def first_run_setup(config: dict) -> dict:
    """Interactive first-run wizard — runs once when no location is set."""
    print("=" * 55)
    print("  Clean Shot — First Run Setup")
    print("  Built for the road, not the boardroom.")
    print("=" * 55)
    print()
    print("No location configured. Let's get you set up.")
    print('Enter a city name, ZIP code, or "City ST".')
    print('Examples: "Memphis TN"  |  "62701"  |  "Flagstaff"')
    print()

    from core.api import geocode_location
    while True:
        try:
            loc = input("Your home base or current location: ").strip()
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

        config["latitude"]  = lat
        config["longitude"] = lon
        config["city"]      = city
        config["home_base"] = city
        print(f"✓ Location set to: {city} ({lat:.4f}, {lon:.4f})")
        break

    print()
    fmt = input("Time format: 12h or 24h? [12h]: ").strip().lower()
    config["time_format"] = "24h" if fmt == "24h" else "12h"

    print()
    print("Vehicle height? Standard semi is ~13.5 ft. Press Enter to skip.")
    try:
        h = input("Height in feet [Enter to skip]: ").strip()
        if h:
            config["vehicle_height_ft"] = float(h)
            print(f"✓ Vehicle height saved: {config['vehicle_height_ft']} ft")
    except (ValueError, EOFError, KeyboardInterrupt):
        pass

    save_config(config)
    print()
    print("Setup complete! Run 'cleanshot' anytime for your forecast.")
    print("Run 'cleanshot help' to see all commands.")
    print()
    return config


# ── Settings display / update ─────────────────────────────────────────────────

def show_settings(config: dict, args: list):
    """Display or update settings from CLI args."""
    print("Clean Shot Settings")
    print("-" * 45)
    city = config.get("city", "Not set")
    lat  = config.get("latitude", "")
    lon  = config.get("longitude", "")
    print(f"Location      : {city}")
    if lat:
        print(f"Coordinates   : {lat:.4f}, {lon:.4f}")
    print(f"Time format   : {config.get('time_format', '12h')}")
    height = config.get("vehicle_height_ft")
    print(f"Vehicle height: {height} ft" if height else "Vehicle height: Not set")
    print(f"Vehicle type  : {config.get('vehicle_type', 'semi')}")
    print(f"Wind alert    : {config.get('wind_alert_mph', 40)} mph")
    print(f"TTS           : {'on' if config.get('tts_enabled') else 'off'}")
    print(f"Subscription  : {config.get('subscription_tier', 'free')}")
    ref_count = config.get("referral_count", 0)
    ref_tier  = config.get("referral_tier", "road_scout")
    print(f"Referrals     : {ref_count} ({ref_tier})")
    print()
    print("To change settings:")
    print("  cleanshot settings 12h           Set 12-hour time")
    print("  cleanshot settings 24h           Set 24-hour time")
    print("  cleanshot settings height 13.5   Set vehicle height")
    print("  cleanshot settings wind 35       Set wind alert threshold")
    print("  cleanshot settings tts on|off    Toggle text-to-speech")
    print("  cleanshot settings location      Change default location")
    print("  cleanshot settings vehicle semi|box|flatbed|tanker|rv")
    print()

    if len(args) < 2:
        return

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

    elif key == "tts" and len(args) >= 3:
        config["tts_enabled"] = args[2].lower() in ("on", "yes", "true", "1")
        save_config(config)
        print(f"✓ TTS {'enabled' if config['tts_enabled'] else 'disabled'}")

    elif key == "vehicle" and len(args) >= 3:
        vtype = args[2].lower()
        valid = {"semi", "box", "flatbed", "tanker", "rv"}
        if vtype in valid:
            config["vehicle_type"] = vtype
            save_config(config)
            print(f"✓ Vehicle type set to {vtype}")
        else:
            print(f"Unknown vehicle type. Options: {', '.join(sorted(valid))}")

    elif key == "location":
        from core.api import geocode_location
        try:
            loc = input("Enter new location: ").strip()
            lat, lon, city = geocode_location(loc)
            if lat:
                config["latitude"]  = lat
                config["longitude"] = lon
                config["city"]      = city
                save_config(config)
                print(f"✓ Location updated to: {city}")
            else:
                print(f"Could not find '{loc}'.")
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")

    else:
        print(f"Unknown setting: {key}")
