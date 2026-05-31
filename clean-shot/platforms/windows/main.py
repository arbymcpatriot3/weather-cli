#!/usr/bin/env python3
# platforms/windows/main.py — Clean Shot: Windows interactive entry point

import sys
import ctypes
import subprocess
import os
import time
import json
import hashlib
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

# ── Session-level flags ───────────────────────────────────────────────────────
_REFERRAL_REMINDER_SHOWN = False


# ── Window setup ──────────────────────────────────────────────────────────────

def _find_bundled_file(filename: str) -> str | None:
    """Locate a file that may be inside a PyInstaller bundle or beside the exe."""
    candidates = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(os.path.join(sys._MEIPASS, filename))
    candidates.append(os.path.join(os.path.dirname(sys.executable), filename))
    candidates.append(os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "..", "..", "assets", filename)
    ))
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _setup_window() -> None:
    """
    Set up the CleanShot console window on Windows.

    MUST be called AFTER at least one print() or sys.stdout.write().
    Without prior I/O, GetConsoleWindow() returns NULL on PyInstaller
    onefile apps and the entire function silently does nothing.

    This was the root cause of Sessions 8 and 12 both failing:
    both called window setup before any console I/O had occurred.
    """
    if sys.platform != "win32":
        return

    try:
        kernel32 = ctypes.windll.kernel32
        user32   = ctypes.windll.user32

        # Step 1: Set the console title
        kernel32.SetConsoleTitleW(f"CleanShot HQ v{VERSION} — Road Intelligence")

        # Step 2: Set buffer size — MUST be taller than the visible window
        #         so the scroll bar appears and resize works.
        #         Using COORD struct (two c_short fields).
        INVALID_HANDLE = ctypes.c_void_p(-1).value
        h = kernel32.GetStdHandle(-11)          # STD_OUTPUT_HANDLE
        if h and h != INVALID_HANDLE:
            class COORD(ctypes.Structure):
                _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]
            kernel32.SetConsoleScreenBufferSize(h, COORD(220, 3000))

        # Step 3: Wait for Windows to finish associating the window handle
        time.sleep(0.15)

        # Step 4: Get the window handle
        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return                  # give up gracefully — never crash

        # Step 5: ONLY ADD style flags, never remove any
        #   WS_CAPTION     = 0x00C00000  (title bar with three buttons)
        #   WS_SYSMENU     = 0x00080000  (close button + system menu)
        #   WS_MINIMIZEBOX = 0x00020000
        #   WS_MAXIMIZEBOX = 0x00010000
        #   WS_THICKFRAME  = 0x00040000  (resizable border)
        GWL_STYLE      = -16
        WS_CAPTION     = 0x00C00000
        WS_SYSMENU     = 0x00080000
        WS_MINIMIZEBOX = 0x00020000
        WS_MAXIMIZEBOX = 0x00010000
        WS_THICKFRAME  = 0x00040000
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        style |= (WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX |
                  WS_MAXIMIZEBOX | WS_THICKFRAME)
        user32.SetWindowLongW(hwnd, GWL_STYLE, style)

        # Step 6: Refresh the frame so buttons appear immediately
        SWP_FLAGS = 0x0020 | 0x0002 | 0x0001 | 0x0004
        # SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_FLAGS)

        # Step 7: Maximize AFTER setting style — order matters
        user32.ShowWindow(hwnd, 3)              # SW_MAXIMIZE = 3

        # Step 8: Set truck icon
        _set_icon(hwnd)

    except Exception:
        pass                        # window setup failure must never crash the app


# Keep the old name as an alias so nothing else breaks
_ensure_full_window = _setup_window


def _set_icon(hwnd: int) -> None:
    """Set the console window's title-bar icon to the truck logo."""
    try:
        icon_path = _find_bundled_file("cleanshot.ico")
        if not icon_path or not os.path.exists(icon_path):
            return
        LR_LOADFROMFILE = 0x0010
        IMAGE_ICON      = 1
        WM_SETICON      = 0x0080
        hicon_big = ctypes.windll.user32.LoadImageW(
            None, icon_path, IMAGE_ICON, 256, 256, LR_LOADFROMFILE
        )
        hicon_small = ctypes.windll.user32.LoadImageW(
            None, icon_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE
        )
        if hicon_big:
            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 1, hicon_big)
        if hicon_small:
            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 0, hicon_small)
    except Exception:
        pass


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


# ── Flyer viewer ─────────────────────────────────────────────────────────────

def open_flyer() -> None:
    """Open the CleanShot product flyer in the default PDF viewer."""
    flyer = _find_bundled_file("CleanShotHQ_Flyer_v9.pdf")
    if flyer:
        try:
            os.startfile(flyer)
            print()
            print("  ✅  Flyer opened in your PDF viewer.")
            print("      Share it with dispatchers, fleet managers, or fellow drivers!")
        except Exception as e:
            print(f"  Could not open flyer: {e}")
    else:
        print()
        print("  ⚠️   Flyer file not found in bundle.")
        print("      Download it at: https://cleanshothq.com/flyer")
    print()
    try:
        input("  Press Enter to return to menu...")
    except (KeyboardInterrupt, EOFError):
        pass
    print()


# ── GPS-speed-aware refresh ───────────────────────────────────────────────────

def get_gps_speed_mph() -> float | None:
    """
    Return current GPS speed in mph, or None if unavailable.
    Tries Windows Location API first, then gpsd (Linux/devices).
    """
    # Windows Location API via WinRT
    try:
        import asyncio
        import winrt.windows.devices.geolocation as _geo

        async def _get():
            loc = _geo.Geolocator()
            pos = await loc.get_geoposition_async()
            spd = pos.coordinate.speed   # m/s or None
            if spd is not None and spd >= 0:
                return spd * 2.23694     # → mph
            return None

        return asyncio.run(_get())
    except Exception:
        pass

    # gpsd (Linux daemon, or devices running gpsd)
    try:
        import gpsd as _gpsd
        _gpsd.connect()
        pkt = _gpsd.get_current()
        if pkt.mode >= 2:
            spd = getattr(pkt, "hspeed", None)
            if spd is not None:
                return spd * 2.23694
    except Exception:
        pass

    return None


def smart_refresh_interval(speed_mph: float | None,
                            manual_minutes: int | None = None) -> int:
    """Return refresh interval in SECONDS based on speed or manual setting."""
    if manual_minutes is not None:
        return manual_minutes * 60
    if speed_mph is None:
        return 5 * 60        # no GPS — default 5 min
    if speed_mph < 5:
        return 20 * 60       # parked
    elif speed_mph < 30:
        return 8 * 60        # city / slow traffic
    elif speed_mph < 55:
        return 4 * 60        # highway approach
    else:
        return 2 * 60        # highway speed


# ── Referral reminder (once per session) ─────────────────────────────────────

def _show_referral_reminder(config: dict) -> None:
    global _REFERRAL_REMINDER_SHOWN
    if _REFERRAL_REMINDER_SHOWN:
        return
    _REFERRAL_REMINDER_SHOWN = True

    count = config.get("referral_count", 0)
    if count >= 5:  # max discount already reached
        return

    ref_code = config.get("referral_code") or ""
    url = (f"https://cleanshothq.com/?ref={ref_code}"
           if ref_code else "https://cleanshothq.com/dashboard")

    print()
    print(f"  💰  Refer a friend → earn $1/mo off your subscription.")
    print(f"      Share: {url}")


# ── Continuous monitor helpers ────────────────────────────────────────────────

def _get_cached_alerts(config: dict) -> list:
    """
    Load current road alerts from the local weather cache.
    Returns [] gracefully if cache is missing or stale.
    No network call — uses whatever _run([]) just wrote.
    """
    try:
        lat = config.get("latitude")
        lon = config.get("longitude")
        if lat is None or lon is None:
            return []
        from core.cache  import cache_load, CACHE_TIME
        from core.alerts import get_road_alerts
        # weather_cache_path is an internal helper; replicate its logic
        import hashlib as _hl, tempfile as _tmp
        cache_dir = Path(_tmp.gettempdir()) / "clean-shot-cache"
        key = _hl.sha256(f"{lat:.4f},{lon:.4f}".encode()).hexdigest()[:16]
        path = cache_dir / f"cs_{key}.json"
        data_str, _ = cache_load(path, CACHE_TIME)
        if not data_str:
            return []
        data = json.loads(data_str)
        return get_road_alerts(data, config) or []
    except Exception:
        return []


def _alert_hash(alerts: list) -> str:
    """Stable hash of alert type+severity combinations."""
    pairs = sorted((a.get("type", ""), a.get("severity", "")) for a in alerts)
    return hashlib.md5(json.dumps(pairs).encode()).hexdigest()


def _speak_new_hazards(new_alerts: list, old_hash: str, config: dict) -> None:
    """Speak and log any critical/high alerts that weren't in the previous cycle."""
    if not new_alerts or not old_hash:
        return
    try:
        from core.tts import speak_alert
        lat = config.get("latitude")
        lon = config.get("longitude")
        for a in new_alerts:
            sev   = a.get("severity", "low").lower()
            atype = a.get("type", "hazard")
            if sev not in ("critical", "high"):
                continue
            speak_alert(atype, sev.upper(), config, distance_mi=None, force=False)
            # Log to Worker (fire-and-forget)
            try:
                from core.hazard_logger import log_hazard
                log_hazard(config, atype, sev,
                           lat=lat, lon=lon, acknowledged=1)
            except Exception:
                pass
    except Exception:
        pass


# ── Continuous monitoring mode ────────────────────────────────────────────────

_INTERVALS = [1, 2, 5, 10, 15, 30]  # allowed refresh intervals in minutes


def continuous_monitor(config: dict | None = None,
                       interval_minutes: int | None = 5,
                       auto_mode: bool = False) -> None:
    """
    Auto-refresh the full dashboard on a timer.
    auto_mode=True: interval adjusts automatically based on GPS speed.
    Keys: Q=quit  R=refresh now  +=longer  -=shorter  A=toggle auto
    """
    try:
        import msvcrt
        _has_msvcrt = True
    except ImportError:
        _has_msvcrt = False

    from core.config import get_config

    if config is None:
        config = get_config()

    if interval_minutes not in _INTERVALS:
        interval_minutes = 5

    prev_hash     = ""
    session_start = int(time.time())
    refresh_count = 0

    print()
    print(f"  Starting Continuous Monitor — {'GPS-auto' if auto_mode else str(interval_minutes) + ' min'} refresh")
    print("  Keys: Q quit  R refresh now  + longer  - shorter  A toggle auto")
    time.sleep(1.2)

    while True:
        # ── GPS speed + smart interval ────────────────────────────────────
        speed_mph = get_gps_speed_mph() if auto_mode else None
        if auto_mode:
            interval_secs = smart_refresh_interval(speed_mph)
            interval_minutes = max(1, interval_secs // 60)
        else:
            interval_secs = (interval_minutes or 5) * 60

        # ── Full dashboard refresh ────────────────────────────────────────
        os.system("cls")
        config = get_config()

        # Build header line
        if auto_mode and speed_mph is not None:
            spd_str = f"🚗 {speed_mph:.0f} mph → {interval_minutes} min refresh"
        elif auto_mode:
            spd_str = f"🔄 GPS unavailable → {interval_minutes} min refresh"
        else:
            spd_str = f"🔄 CONTINUOUS MODE  [{interval_minutes} min]"

        print(f"  {'═' * 56}")
        print(f"  {spd_str}  —  Q quit  R now  +/- interval  A auto")
        print(f"  {'═' * 56}")
        print()

        _run([])
        refresh_count += 1

        # ── New-hazard check (after cache is fresh from _run) ─────────────
        new_alerts = _get_cached_alerts(config)
        new_hash   = _alert_hash(new_alerts)

        if prev_hash and new_hash != prev_hash:
            _speak_new_hazards(new_alerts, prev_hash, config)

        prev_hash = new_hash

        # ── Countdown with non-blocking key input ─────────────────────────
        end_time = time.time() + interval_secs
        try:
            while time.time() < end_time:
                remaining = max(0, int(end_time - time.time()))
                m, s = divmod(remaining, 60)
                print(
                    f"\r  Next refresh in {m:02d}:{s:02d}"
                    f"  —  Q quit  R now  + longer  - shorter   ",
                    end="", flush=True,
                )

                if _has_msvcrt and msvcrt.kbhit():
                    raw = msvcrt.getch()
                    # Special keys (arrows, F-keys) send 2 bytes; consume both
                    if raw in (b"\x00", b"\xe0"):
                        if msvcrt.kbhit():
                            msvcrt.getch()
                        time.sleep(0.1)
                        continue

                    try:
                        k = raw.decode("utf-8", errors="ignore").lower()
                    except Exception:
                        k = ""

                    if k in ("q", "\x1b", "\x03"):       # Q / Esc / Ctrl-C
                        print("\n")
                        _end_monitor_session(session_start, refresh_count, config)
                        return

                    elif k in ("r", "\r", "\n"):           # R or Enter → refresh now
                        print()
                        break

                    elif k == "+":
                        auto_mode = False
                        idx = (_INTERVALS.index(interval_minutes)
                               if interval_minutes in _INTERVALS else 2)
                        interval_minutes = _INTERVALS[min(idx + 1, len(_INTERVALS) - 1)]
                        end_time = time.time() + interval_minutes * 60
                        print(f"\r  Interval set to {interval_minutes} min" + " " * 30,
                              end="", flush=True)

                    elif k == "-":
                        auto_mode = False
                        idx = (_INTERVALS.index(interval_minutes)
                               if interval_minutes in _INTERVALS else 2)
                        interval_minutes = _INTERVALS[max(idx - 1, 0)]
                        end_time = time.time() + interval_minutes * 60
                        print(f"\r  Interval set to {interval_minutes} min" + " " * 30,
                              end="", flush=True)

                    elif k == "a":
                        auto_mode = not auto_mode
                        mode_str = "GPS auto" if auto_mode else f"{interval_minutes} min manual"
                        print(f"\r  Mode: {mode_str}" + " " * 30,
                              end="", flush=True)

                time.sleep(0.4)

        except KeyboardInterrupt:
            print("\n")
            _end_monitor_session(session_start, refresh_count, config)
            return


def _end_monitor_session(session_start: int, refresh_count: int,
                         config: dict) -> None:
    """Log the completed session to the Worker and print goodbye."""
    try:
        from core.hazard_logger import log_session
        log_session(
            config,
            queries=refresh_count,
            session_start=session_start,
        )
    except Exception:
        pass
    print("  Continuous mode ended. Drive safe. 🛡️")
    print()


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
    print("  C  Continuous Monitor  (auto-refresh)")
    print("  F  View Flyer / Share Info")
    print("  ?  Help & Icon Glossary")
    print("  0  Exit")
    print(_DIV)


# ── Interactive loop ──────────────────────────────────────────────────────────

def _interactive_loop() -> None:
    """Show the full weather report, then keep the window open with a menu."""
    from core.config import get_config

    # A write to stdout MUST happen before _setup_window() is called.
    # On PyInstaller onefile apps, GetConsoleWindow() returns NULL until
    # at least one I/O operation has occurred — sleep() alone does not fix this.
    # This was the root cause of Sessions 8 and 12 both silently failing.
    print()
    _setup_window()
    _run([])   # full report on startup

    # Referral reminder — once per session, after first display
    try:
        config = get_config()
        _show_referral_reminder(config)
    except Exception:
        pass

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

        elif raw.lower() in ("c", "monitor", "watch"):
            try:
                from core.config import get_config as _gc
                _cfg = _gc()
                mins_str = input(
                    "  Refresh interval [1/2/5/10/15/30/A=GPS-auto] (Enter = 5 min): "
                ).strip().lower()
                if mins_str == "a":
                    print()
                    continuous_monitor(_cfg, interval_minutes=5, auto_mode=True)
                else:
                    mins = int(mins_str) if mins_str.isdigit() else 5
                    if mins not in _INTERVALS:
                        mins = min(_INTERVALS, key=lambda x: abs(x - mins))
                        print(f"  Using {mins} min (nearest valid interval)")
                    print()
                    continuous_monitor(_cfg, interval_minutes=mins, auto_mode=False)
            except (KeyboardInterrupt, EOFError):
                print()

        elif raw.lower() in ("f", "flyer"):
            open_flyer()

        elif raw in ("?", "help", "h"):
            try:
                from core.glossary import show_glossary
                from core.config   import get_config as _gc
                show_glossary(_gc())
            except Exception as e:
                print(f"  Glossary unavailable: {e}")

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
