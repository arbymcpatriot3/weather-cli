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
    "time_format":           "12h",
    "units":                 "imperial",
    "display_width_override": None,   # int or None — force a width (36–300)
    # Vehicle
    "vehicle_height_ft": None,
    "vehicle_type":      "semi",      # semi | box | flatbed | tanker | rv
    # Alerts
    "wind_alert_mph":    40,
    # Features
    "tts_enabled":       False,
    "voice_enabled":     False,
    "offline_mode":      False,
    # Driver profile
    "driver_name":       None,        # set during first_run_setup
    # Account
    "driver_id":         None,
    "subscription_tier": "free",      # free | solo_pro | pro_plus | fleet | enterprise
    "referral_code":     None,
    "home_base":         None,
    # Referral stats (local cache — source of truth is server)
    "referral_count":    0,
    "referral_tier":     "road_scout", # road_scout → captain → commander → legend → elite → ambassador
    # TTS
    "tts_repeat_suppress_min": 30,     # minutes before repeating same alert
    "quiet_hours_start": None,         # "22:00" or None to disable
    "quiet_hours_end":   None,         # "06:00" or None to disable
    "tts_speed_aware":   True,         # WARNING/INFO wait until parked
    "tts_voice_quality": "enhanced",   # standard (espeak) | enhanced (festival) | premium (piper)
    "tts_voice_name":    "en_US-ryan-high",  # piper voice model name (ryan-high approved)
    "tts_rate":          150,          # words per minute (80–300)
    "tts_volume":        0.9,          # 0.0 – 1.0
    # Alert tones
    "tts_tone_enabled":  True,         # play distinctive tone before each spoken alert
    "tts_tone_volume":   0.8,          # tone volume 0.0–1.0 (config: 1-10 maps to 0.0-1.0)
    "tts_repeat_timeout": 10,          # seconds before auto-continue on repeat prompt
    # macOS voice preference
    "tts_macos_voice":   "Samantha",   # macOS say -v <voice>: Samantha | Alex
    # Last 3 spoken messages (for Hey Clean Shot, repeat)
    "tts_last_messages": [],
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
    sep = "━" * 35

    print()
    print(f"  {sep}")
    print(f"  🚛 WELCOME TO CLEAN SHOT v{VERSION[:3]}")
    print(f"     By Blue Collar Nation LLC")
    print(f"     cleanshothq.com")
    print(f"  {sep}")
    print()
    print("  Built for the road,")
    print("  not the boardroom.")
    print()
    print("  Quick setup — just 3 questions:")
    print()

    # ── Q1: Name (optional) ───────────────────────────────────────────────────
    try:
        print("  1. Your name (optional):")
        name = input("     > ").strip()
        if name:
            config["driver_name"] = name
    except (EOFError, KeyboardInterrupt):
        print("\n  Setup cancelled.")
        sys.exit(0)

    # ── Q2: Location ──────────────────────────────────────────────────────────
    print()
    print("  2. Your location:")
    print("     City, State or ZIP code")
    print("     (or press Enter to auto-detect)")

    from core.api import geocode_location, get_auto_location

    while True:
        try:
            loc = input("     > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Setup cancelled.")
            sys.exit(0)

        if not loc:
            print("     Auto-detecting your location...")
            try:
                lat, lon, city = get_auto_location()
            except Exception:
                lat = None
            if lat is not None:
                config["latitude"]  = lat
                config["longitude"] = lon
                config["city"]      = city
                config["home_base"] = city
                print(f"     Found: {city}")
                break
            else:
                print("     Could not auto-detect.")
                print("     Please enter City, State or ZIP:")
                continue

        lat, lon, city = geocode_location(loc)
        if lat is not None:
            config["latitude"]  = lat
            config["longitude"] = lon
            config["city"]      = city
            config["home_base"] = city
            print(f"     ✓ {city}")
            break
        else:
            print(f"     Can't find that location.")
            print(f"     Try: Memphis TN  |  38101  |  Chicago")

    # ── Q3: Vehicle type ──────────────────────────────────────────────────────
    print()
    print("  3. Your vehicle type:")
    print("     1. Diesel truck")
    print("     2. Gas truck")
    print("     3. Electric truck (EV)")
    print("     4. Hybrid")
    print("     5. Other")

    _vmap = {"1": "semi", "2": "box", "3": "semi", "4": "box", "5": "semi"}
    while True:
        try:
            choice = input("     > ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = "1"
        if choice in _vmap:
            config["vehicle_type"] = _vmap[choice]
            break
        if not choice:
            config["vehicle_type"] = "semi"
            break
        print("     Enter 1–5")

    save_config(config)

    # ── Welcome screen ────────────────────────────────────────────────────────
    driver_name = config.get("driver_name", "")
    greeting = f"Welcome aboard {driver_name}!" if driver_name else "You're all set!"

    print()
    print(f"  {sep}")
    print(f"  ✅ {greeting}")
    print(f"     You have 30 days free.")
    print(f"     No credit card needed.")
    print()
    print(f"     Type: cleanshot")
    print(f"     For help: cleanshot help")
    print(f"     Check system: cleanshot doctor")
    print()
    print(f"     \"Roads are clean and green.")
    print(f"      Welcome to Clean Shot")
    print(f"      good buddy.\" 🚛")
    print(f"  {sep}")
    print()

    # ── TTS welcome ───────────────────────────────────────────────────────────
    try:
        from core.tts import speak
        _tts_cfg = dict(config)
        _tts_cfg["tts_enabled"] = True
        speak(
            "Roads are clean and green. "
            "Welcome to Clean Shot good buddy.",
            _tts_cfg,
        )
    except Exception:
        pass

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
    print(f"TTS quality   : {config.get('tts_voice_quality', 'enhanced')}  (standard/enhanced/premium)")
    print(f"TTS voice     : {config.get('tts_voice_name', 'en_US-ryan-high')}  (piper model)")
    print(f"TTS rate      : {config.get('tts_rate', 150)} WPM")
    print(f"TTS volume    : {config.get('tts_volume', 0.9)}")
    print(f"Alert tones   : {'on' if config.get('tts_tone_enabled', True) else 'off'}")
    tone_vol = int(config.get('tts_tone_volume', 0.8) * 10)
    print(f"Tone volume   : {tone_vol}/10")
    print(f"Repeat timeout: {config.get('tts_repeat_timeout', 10)}s")
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
    print("  cleanshot settings tts on|off              Toggle text-to-speech")
    print("  cleanshot settings tts-quality enhanced     standard/enhanced/premium")
    print("  cleanshot settings tts-rate 150             Words per minute (80-300)")
    print("  cleanshot settings tts-volume 0.9           Volume (0.0-1.0)")
    print("  cleanshot settings voice list               Show piper voices")
    print("  cleanshot settings voice ryan               Set voice (shorthand)")
    print("  cleanshot settings voice en_US-ryan-high    Set voice (full name)")
    print("  cleanshot settings tone on|off              Enable/disable alert tones")
    print("  cleanshot settings tone-volume 8            Tone volume 1-10")
    print("  cleanshot settings repeat-timeout 15        Auto-continue delay (seconds)")
    print("  cleanshot voices download                   Download default voice")
    print("  cleanshot fix-voice                         Restore natural voice")
    print("  cleanshot settings location                 Change default location")
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

    elif key == "tts-quality" and len(args) >= 3:
        q = args[2].lower()
        if q in ("standard", "enhanced", "premium"):
            config["tts_voice_quality"] = q
            save_config(config)
            print(f"✓ TTS quality set to {q}")
        else:
            print("Options: standard, enhanced, premium")

    elif key == "tts-rate" and len(args) >= 3:
        try:
            r = int(args[2])
            if 80 <= r <= 300:
                config["tts_rate"] = r
                save_config(config)
                print(f"✓ TTS rate set to {r} WPM")
            else:
                print("Rate must be 80–300 WPM")
        except ValueError:
            print("Invalid rate. Example: cleanshot settings tts-rate 150")

    elif key == "tts-volume" and len(args) >= 3:
        try:
            v = float(args[2])
            if 0.0 <= v <= 1.0:
                config["tts_volume"] = v
                save_config(config)
                print(f"✓ TTS volume set to {v}")
            else:
                print("Volume must be 0.0–1.0")
        except ValueError:
            print("Invalid volume. Example: cleanshot settings tts-volume 0.9")

    elif key == "vehicle" and len(args) >= 3:
        vtype = args[2].lower()
        valid = {"semi", "box", "flatbed", "tanker", "rv"}
        if vtype in valid:
            config["vehicle_type"] = vtype
            save_config(config)
            print(f"✓ Vehicle type set to {vtype}")
        else:
            print(f"Unknown vehicle type. Options: {', '.join(sorted(valid))}")

    elif key == "tone" and len(args) >= 3:
        config["tts_tone_enabled"] = args[2].lower() in ("on", "yes", "true", "1")
        save_config(config)
        print(f"✓ Alert tones {'enabled' if config['tts_tone_enabled'] else 'disabled'}")

    elif key == "tone-volume" and len(args) >= 3:
        try:
            v = int(args[2])
            if 1 <= v <= 10:
                config["tts_tone_volume"] = round(v / 10, 1)
                save_config(config)
                print(f"✓ Tone volume set to {v}/10")
            else:
                print("Tone volume must be 1–10")
        except ValueError:
            print("Invalid value. Example: cleanshot settings tone-volume 8")

    elif key == "repeat-timeout" and len(args) >= 3:
        try:
            t_val = int(args[2])
            if 5 <= t_val <= 120:
                config["tts_repeat_timeout"] = t_val
                save_config(config)
                print(f"✓ Repeat timeout set to {t_val}s")
            else:
                print("Timeout must be 5–120 seconds")
        except ValueError:
            print("Invalid value. Example: cleanshot settings repeat-timeout 15")

    elif key == "voice" and len(args) >= 3:
        sub = args[2].lower()
        if sub == "list":
            try:
                from platforms.linux.tts_linux import list_voices
                list_voices(config)
            except ImportError:
                print("Voice listing only available on Linux.")
        else:
            # Resolve short alias (ryan → en_US-ryan-high)
            try:
                from platforms.linux.tts_linux import PIPER_VOICES, _voice_is_installed, resolve_voice_alias
                full_name = resolve_voice_alias(sub)
                if full_name in PIPER_VOICES:
                    config["tts_voice_name"] = full_name
                    save_config(config)
                    if _voice_is_installed(full_name):
                        print(f"✓ Voice set to {full_name}")
                    else:
                        print(f"✓ Voice set to {full_name}")
                        print(f"  (model not downloaded yet)")
                        print(f"  Run: cleanshot voices download {full_name}")
                else:
                    print(f"Unknown voice: {sub}")
                    print("  Run: cleanshot voices  to see available voices")
            except ImportError:
                print("Voice selection only available on Linux.")

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
