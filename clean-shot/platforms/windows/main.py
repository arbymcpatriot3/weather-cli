#!/usr/bin/env python3
# platforms/windows/main.py — Clean Shot: Windows interactive entry point

import sys
import ctypes
from pathlib import Path

# ── Windows console: force UTF-8 before any import triggers output ────────────
try:
    ctypes.windll.kernel32.SetConsoleCP(65001)
    ctypes.windll.kernel32.SetConsoleOutputCP(65001)
except Exception:
    pass

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Path setup ────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.weather import main, VERSION  # noqa: E402

# ── Shared divider ────────────────────────────────────────────────────────────
_DIV = "─" * 56


# ── Command runner ────────────────────────────────────────────────────────────

def _run(cmd_args: list) -> None:
    """Invoke core.weather.main() with a temporary sys.argv, then restore it."""
    saved = sys.argv[:]
    sys.argv = ["cleanshot"] + cmd_args
    try:
        main()
    except SystemExit:
        pass
    except KeyboardInterrupt:
        print("\n  (interrupted)")
    finally:
        sys.argv = saved


# ── Settings sub-menu ─────────────────────────────────────────────────────────

def _settings_menu() -> None:
    """Interactive settings — reads and writes config directly."""
    from core.config import get_config, save_config
    from core.api   import geocode_location

    _FUEL_LABELS = {
        "diesel":   "Diesel",
        "gasoline": "Gasoline",
        "electric": "Electric (EV)",
        "hybrid":   "Hybrid",
        "other":    "Other",
    }
    _VEH_LABELS = {
        "semi":    "Semi / 18-wheeler",
        "box":     "Box truck",
        "flatbed": "Flatbed",
        "tanker":  "Tanker",
        "rv":      "RV / other",
    }

    while True:
        config = get_config()

        name   = config.get("driver_name")   or "not set"
        city   = config.get("city")          or "not set"
        fuel   = _FUEL_LABELS.get(config.get("fuel_type",    "diesel"),  "Diesel")
        vtype  = _VEH_LABELS.get(config.get("vehicle_type",  "semi"),    "Semi")
        height = config.get("vehicle_height_ft")
        tts    = "ON"  if config.get("tts_enabled", True)  else "OFF"
        wind   = config.get("wind_alert_mph", 40)
        tfmt   = config.get("time_format", "12h")

        print()
        print(_DIV)
        print("  Settings")
        print(_DIV)
        print(f"  1  Driver name        {name}")
        print(f"  2  Home location      {city}")
        print(f"  3  Fuel type          {fuel}")
        print(f"  4  Vehicle type       {vtype}")
        print(f"  5  Vehicle height     {str(height) + ' ft' if height else 'not set'}")
        print(f"  6  Voice alerts       {tts}")
        print(f"  7  Wind alert         {wind} mph")
        print(f"  8  Time format        {tfmt}")
        print(f"  0  Back to main menu")
        print(_DIV)

        try:
            choice = input("  Change setting #: ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if choice in ("0", ""):
            break

        elif choice == "1":
            try:
                val = input("  Your name: ").strip()
                if val:
                    config["driver_name"] = val
                    save_config(config)
                    print(f"  Saved: {val}")
            except (KeyboardInterrupt, EOFError):
                print()

        elif choice == "2":
            try:
                loc = input("  City or ZIP code: ").strip()
                if loc:
                    print("  Looking up...")
                    lat, lon, city_name = geocode_location(loc)
                    if lat is not None:
                        config["latitude"]  = lat
                        config["longitude"] = lon
                        config["city"]      = city_name
                        save_config(config)
                        print(f"  Saved: {city_name}")
                    else:
                        print(f"  Could not find '{loc}'. Try: Memphis TN | 38101")
            except (KeyboardInterrupt, EOFError):
                print()

        elif choice == "3":
            print("  1  Diesel")
            print("  2  Gasoline")
            print("  3  Electric (EV)")
            print("  4  Hybrid")
            print("  5  Other / natural gas")
            try:
                fc = input("  Choice: ").strip()
                fmap = {"1": "diesel", "2": "gasoline", "3": "electric",
                        "4": "hybrid", "5": "other"}
                if fc in fmap:
                    config["fuel_type"] = fmap[fc]
                    save_config(config)
                    print(f"  Saved: {_FUEL_LABELS[fmap[fc]]}")
            except (KeyboardInterrupt, EOFError):
                print()

        elif choice == "4":
            print("  1  Semi / 18-wheeler")
            print("  2  Box truck")
            print("  3  Flatbed")
            print("  4  Tanker")
            print("  5  RV / other")
            try:
                vc = input("  Choice: ").strip()
                vmap = {"1": "semi", "2": "box", "3": "flatbed",
                        "4": "tanker", "5": "rv"}
                if vc in vmap:
                    config["vehicle_type"] = vmap[vc]
                    save_config(config)
                    print(f"  Saved: {_VEH_LABELS[vmap[vc]]}")
            except (KeyboardInterrupt, EOFError):
                print()

        elif choice == "5":
            try:
                val = input("  Height in feet (e.g. 13.5): ").strip()
                if val:
                    config["vehicle_height_ft"] = float(val)
                    save_config(config)
                    print(f"  Saved: {val} ft")
            except (ValueError, KeyboardInterrupt, EOFError):
                print("  Invalid value. Example: 13.5")

        elif choice == "6":
            config["tts_enabled"] = not config.get("tts_enabled", True)
            save_config(config)
            status = "ON" if config["tts_enabled"] else "OFF"
            print(f"  Voice alerts: {status}")
            if config["tts_enabled"]:
                print("  Testing voice now...")
                try:
                    from core.tts import speak
                    speak("Clean Shot voice alerts are now active. Drive safe.",
                          config, bypass_quiet=True)
                except Exception:
                    print("  (voice test failed — check sound settings)")

        elif choice == "7":
            try:
                val = input("  Wind alert threshold in mph (e.g. 40): ").strip()
                if val:
                    config["wind_alert_mph"] = float(val)
                    save_config(config)
                    print(f"  Saved: {val} mph")
            except (ValueError, KeyboardInterrupt, EOFError):
                print("  Invalid value. Example: 40")

        elif choice == "8":
            try:
                val = input("  Time format — enter 12h or 24h: ").strip().lower()
                if val in ("12h", "24h"):
                    config["time_format"] = val
                    save_config(config)
                    print(f"  Saved: {val}")
                elif val:
                    print("  Enter 12h or 24h")
            except (KeyboardInterrupt, EOFError):
                print()

        else:
            print("  Enter a number from the list above.")


# ── Main menu ─────────────────────────────────────────────────────────────────

def _menu() -> None:
    print()
    print(_DIV)
    print(f"  Clean Shot v{VERSION} — What would you like to do?")
    print(_DIV)
    print("  1  Refresh weather report")
    print("  2  Simple one-line summary")
    print("  3  Compact view")
    print("  4  Active weather alerts")
    print("  5  Route weather  (enter two cities)")
    print("  6  Regional map")
    print("  7  Settings")
    print("  8  Doctor  (system health check)")
    print("  9  Help")
    print("  0  Exit")
    print(_DIV)


def _ensure_console_size(cols: int = 120, lines: int = 50) -> None:
    """Grow the console window to at least cols×lines on first interactive launch."""
    try:
        import subprocess
        subprocess.run(
            ["mode", "con:", f"cols={cols}", f"lines={lines}"],
            shell=True,
            capture_output=True,
        )
    except Exception:
        pass


def _interactive_loop() -> None:
    """Show the full weather report, then keep the window open with a menu."""
    _ensure_console_size()
    _run([])   # full report on startup

    while True:
        _menu()

        try:
            raw = input("  Choice (or Enter to refresh): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n  Drive safe.")
            break

        print()

        if raw in ("0", "exit", "quit", "q", "x"):
            print("  Drive safe.")
            break

        elif raw in ("", "1"):
            _run([])

        elif raw == "2":
            _run(["simple"])

        elif raw == "3":
            _run(["compact"])

        elif raw == "4":
            _run(["alerts"])

        elif raw == "5":
            try:
                start = input("  Start city / ZIP: ").strip()
                end   = input("  End city   / ZIP: ").strip()
                if start and end:
                    print()
                    _run(["route", start, end])
                else:
                    print("  Route needs both a start and end location.")
            except (KeyboardInterrupt, EOFError):
                print()

        elif raw == "6":
            _run(["map"])

        elif raw == "7":
            _settings_menu()

        elif raw == "8":
            _run(["doctor"])

        elif raw == "9":
            _run(["help"])

        else:
            # Treat unrecognised input as a location lookup
            print(f"  Looking up: {raw}")
            _run(["--location", raw])


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # CLI usage (cleanshot simple, cleanshot --version, etc.) — run once, exit.
        try:
            main()
        except SystemExit as e:
            sys.exit(e.code)
    else:
        # Double-click / shortcut launch — interactive loop, stays open.
        _interactive_loop()
