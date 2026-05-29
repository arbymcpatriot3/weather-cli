#!/usr/bin/env python3
# display/full.py — Clean Shot: full weather display (current, hourly, forecast)
# Migrated from display.py v2.0.0
# Fully responsive to terminal width — supports 36-char Android phones to 120+ terminals.
#
# Width modes (use display_mode(w) to query):
#   ultra_compact : w < 40  — single-line emoji format, 36-char Android minimum
#   compact       : w 40-59 — two-line abbreviated format
#   standard      : w 60-79 — current labeled format
#   full          : w 80+   — full detail with descriptions

import shutil
from colorama import Fore, Style, init
from core.parse import degrees_to_dir

init(autoreset=True)


# ── Terminal width helpers ────────────────────────────────────────────────────

def get_width() -> int:
    """
    Actual terminal width, uncapped.  Minimum 36 (narrowest supported).
    Callers that want a content cap should use min(get_width(), 80) themselves.
    """
    return max(36, shutil.get_terminal_size(fallback=(80, 24)).columns)


def _get_w(config=None) -> int:
    """
    Effective display width, respecting config["display_width_override"].
    Use this in any function that needs the correct current width.
    """
    if config:
        override = config.get("display_width_override")
        if override and isinstance(override, int) and 20 <= override <= 300:
            return override
    return get_width()


def display_mode(width: int) -> str:
    """
    Return the display density mode for a given terminal width.
    ultra_compact : < 40   (Android phones, Bold Blu K50, etc.)
    compact       : 40-59  (small tablets)
    standard      : 60-79  (laptop, older terminals)
    full          : 80+    (desktop, wide terminals)
    """
    if width < 40:
        return "ultra_compact"
    if width < 60:
        return "compact"
    if width < 80:
        return "standard"
    return "full"


def separator(width: int, char: str = "─") -> str:
    """Return a separator line of exactly `width` characters."""
    return char * max(1, width)


def _trunc(text: str, max_len: int) -> str:
    """Truncate text to max_len, appending '…' if cut."""
    if len(text) <= max_len:
        return text
    return text[:max(1, max_len - 1)] + "…"


def print_header(title: str, width: int, version: str = ""):
    """Print a boxed header scaled to `width`."""
    w   = max(10, width)
    ver = f"  v{version}" if version else ""

    if display_mode(w) == "ultra_compact":
        # No box — just a title line with separator
        label = _trunc(f"Clean Shot{ver}", w)
        print(separator(w, "━"))
        print(label.center(w))
        print(separator(w, "━"))
        print()
        return

    full_title = f"  {title}{ver}  "
    if len(full_title) > w - 2:
        full_title = full_title[:w - 5] + "…  "
    bar = "─" * (w - 2)
    pad = max(0, w - 2 - len(full_title))
    print(f"┌{bar}┐")
    print(f"│{full_title}{' ' * pad}│")
    print(f"└{bar}┘")
    print()


# ── Color helpers ─────────────────────────────────────────────────────────────

def temp_color(temp: float) -> str:
    if temp < 32:
        return Fore.CYAN
    elif temp < 50:
        return Fore.BLUE
    elif temp < 70:
        return Fore.GREEN
    elif temp < 85:
        return Fore.YELLOW
    else:
        return Fore.RED


def wind_color(speed: float, alert_mph: float = 40) -> str:
    if speed >= alert_mph:
        return Fore.RED
    elif speed >= alert_mph * 0.75:
        return Fore.YELLOW
    else:
        return Fore.GREEN


# ── Simple one-liner ──────────────────────────────────────────────────────────

def display_simple(parsed: dict):
    cur  = parsed["current"]
    city = parsed["city"]
    print(f"{cur['temp']:.1f}°F  {cur['desc_short']}  {city}")


# ── Compact 80-column ─────────────────────────────────────────────────────────

def display_compact(parsed: dict, width: int):
    cur  = parsed["current"]
    fc   = parsed["forecast"][0]
    city = parsed["city"]
    w    = width

    print("-" * w)
    print(_trunc(f"  {city}", w).center(w))
    print("-" * w)
    if display_mode(w) == "ultra_compact":
        print(f"🌡{cur['temp']:.0f}°F ({cur['feels']:.0f}) {cur['desc_short'][:12]}")
        print(f"💨{cur['wind_speed']:.0f}mph {degrees_to_dir(cur['wind_dir'])}")
        print(f"📅Hi:{fc['high']:.0f} Lo:{fc['low']:.0f} 🌧{fc['rain_prob']:.0f}%")
    else:
        print(f"  Now:   {cur['temp']:>5.1f}°F  (feels {cur['feels']:.1f}°F)")
        print(f"  Cond:  {cur['desc_short']}")
        print(f"  Wind:  {cur['wind_speed']:>5.1f} mph  {degrees_to_dir(cur['wind_dir'])}")
        print(f"  Today: High {fc['high']:.0f}°  Low {fc['low']:.0f}°  Rain {fc['rain_prob']:.0f}%")
    print("-" * w)


# ── Current conditions block ──────────────────────────────────────────────────

def display_current(parsed: dict, width: int):
    cur   = parsed["current"]
    fc    = parsed["forecast"][0]
    city  = parsed["city"]
    ts    = parsed["timestamp"]
    w     = width
    mode  = display_mode(w)

    cache_age = parsed.get("cache_age", 0)
    cache_str = f" (cached {cache_age}m)" if cache_age > 0 else ""

    if mode == "ultra_compact":
        # ── Ultra-compact: emoji-first, single line per datum ─────────────────
        print(separator(w, "━"))
        print(_trunc(f"📍{city}{cache_str}", w))
        tc = temp_color(cur["temp"])
        print(f"{tc}🌡{cur['temp']:.0f}°F{Style.RESET_ALL} {cur['desc_short'][:14]}")
        ws = cur["wind_speed"]
        if ws >= 1:
            wg  = cur["wind_gust"]
            wd  = degrees_to_dir(cur["wind_dir"])
            wc  = wind_color(ws, parsed.get("wind_alert_mph", 40))
            g   = f"g{wg:.0f}" if wg > ws + 5 else ""
            print(f"{wc}💨{ws:.0f}mph {wd}{g}{Style.RESET_ALL}")
        print(f"💧{cur['humidity']:.0f}% | 🌅{fc['sunrise']}↑{fc['sunset']}↓")
        return

    if mode == "compact":
        # ── Compact: abbreviated labels ────────────────────────────────────────
        print(separator(w))
        print(_trunc(f"📍 {city}{cache_str}", w))
        tc = temp_color(cur["temp"])
        _cond = _trunc(cur['desc_short'], max(1, w - 27))
        print(f"  {tc}{cur['temp']:.1f}°F{Style.RESET_ALL} (feels {cur['feels']:.1f}) — {_cond}")
        ws  = cur["wind_speed"]
        wc  = wind_color(ws, parsed.get("wind_alert_mph", 40))
        wg  = cur["wind_gust"]
        g   = f" g{wg:.0f}" if wg > ws + 5 else ""
        wd  = degrees_to_dir(cur["wind_dir"])
        print(f"  {wc}💨 {ws:.0f}mph {wd}{g}{Style.RESET_ALL}  💧{cur['humidity']:.0f}%")
        return

    # ── Standard / Full ───────────────────────────────────────────────────────
    print(f"Location: {_trunc(city, w - 10)}")
    print(f"Updated:  {ts}{cache_str}")
    print()
    print("Current Conditions")
    print(separator(w))

    tc = temp_color(cur["temp"])
    print(f"Temperature     : {tc}{cur['temp']:.1f}°F{Style.RESET_ALL}  "
          f"(feels like {cur['feels']:.1f}°F)")
    print(f"Condition       : {cur['desc_short']}")
    print(f"Humidity        : {cur['humidity']:.0f}%")

    ws = cur["wind_speed"]
    wd = degrees_to_dir(cur["wind_dir"])
    wg = cur["wind_gust"]
    wc = wind_color(ws, parsed.get("wind_alert_mph", 40))
    if ws < 1:
        print("Wind            : Calm")
    else:
        gust_str = f"  (gusts {wg:.1f} mph)" if wg > ws + 5 else ""
        print(f"Wind            : {wc}{ws:.1f} mph  {wd}{Style.RESET_ALL}{gust_str}")

    print(f"Sunrise / Sunset: {fc['sunrise']}  /  {fc['sunset']}")


# ── Alerts block ──────────────────────────────────────────────────────────────

def display_alerts(alerts: list, width: int):
    if not alerts:
        return
    w    = width
    mode = display_mode(w)
    print()
    print(f"{Fore.RED}{separator(w)}{Style.RESET_ALL}")
    if mode == "ultra_compact":
        print(f"{Fore.RED}⚠ WEATHER ALERTS{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}⚠  ACTIVE WEATHER ALERTS{Style.RESET_ALL}")
    print(f"{Fore.RED}{separator(w)}{Style.RESET_ALL}")
    for a in alerts:
        sev   = a.get("severity", "")
        color = (Fore.RED   if sev == "Extreme" else
                 Fore.YELLOW if sev == "Severe"  else
                 Fore.WHITE)
        event = _trunc(a["event"], w - 4)
        print(f"{color}• {event}{Style.RESET_ALL}")
        if a.get("headline") and mode not in ("ultra_compact",):
            hl = _trunc(a["headline"], w - 4)
            print(f"  {hl}")
    print(f"{Fore.RED}{separator(w)}{Style.RESET_ALL}")


# ── Trucker wind alert ────────────────────────────────────────────────────────

def display_wind_alert(hourly: dict, alert_mph: float, width: int):
    gusts = hourly.get("wind_gusts", [0] * 24)
    if not gusts:
        return
    max_gust = max(gusts)
    if max_gust >= alert_mph:
        w    = width
        mode = display_mode(w)
        print()
        if mode == "ultra_compact":
            print(f"{Fore.RED}⚠ WIND {max_gust:.0f}mph — secure loads{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}⚠  TRUCKER WIND ALERT: Gusts up to {max_gust:.1f} mph in next 24h{Style.RESET_ALL}")
            print(f"{Fore.RED}   Secure all loads! High-profile vehicle caution advised.{Style.RESET_ALL}")


# ── Hourly chart ──────────────────────────────────────────────────────────────

def display_hourly(hourly: dict, width: int, time_format: str = "12h",
                   alert_mph: float = 40):
    w    = width
    mode = display_mode(w)
    print()

    temps = hourly["temps"]
    gusts = hourly.get("wind_gusts", [0] * 24)
    probs = hourly.get("precip_probs", [0] * 24)
    tz    = hourly.get("tz_label", "")

    if mode == "ultra_compact":
        # ── Ultra-compact: next 6 hours, no bar ───────────────────────────────
        print(f"─Next 6h{'─'*(w-8)}" if w > 8 else "─"*w)
        for i in range(min(6, len(temps))):
            dt   = hourly["times_parsed"][i]
            temp = temps[i]
            gust = gusts[i] if i < len(gusts) else 0
            rain = probs[i]  if i < len(probs) else 0
            tc   = temp_color(temp)
            ts   = dt.strftime("%H") if time_format == "24h" else dt.strftime("%-I%p").lower()
            gstr = f" 💨{gust:.0f}" if gust >= alert_mph else ""
            rstr = f" 🌧{rain:.0f}%" if rain >= 20 else ""
            print(f"{ts} {tc}{temp:.0f}°{Style.RESET_ALL}{gstr}{rstr}")
        return

    if mode == "compact":
        # ── Compact: 12 hours, no bar chart ───────────────────────────────────
        print(f"Hourly — Next 12h")
        print(separator(w))
        for i in range(min(12, len(temps))):
            dt   = hourly["times_parsed"][i]
            temp = temps[i]
            gust = gusts[i] if i < len(gusts) else 0
            rain = probs[i]  if i < len(probs) else 0
            tc   = temp_color(temp)
            gc   = Fore.RED if gust >= alert_mph else ""
            ts   = dt.strftime("%H:%M") if time_format == "24h" else dt.strftime("%-I:%M%p")
            rstr = f" 🌧{rain:.0f}%" if rain >= 20 else ""
            gstr = f" {gc}💨{gust:.0f}{Style.RESET_ALL}" if gust > 5 else ""
            print(f"{ts} {tc}{temp:.0f}°F{Style.RESET_ALL}{gstr}{rstr}")
        return

    # ── Standard / Full: 24 hours with bar ────────────────────────────────────
    # Reserve room for gust (~11 chars) + rain (~7 chars) annotations
    max_bar = max(4, w - 48)

    print("Hourly Forecast (Next 24 hours)")
    print(separator(w))

    max_t   = max(temps) if temps else 100
    min_t   = min(temps) if temps else 0
    t_range = max_t - min_t if max_t != min_t else 1

    for i in range(24):
        dt   = hourly["times_parsed"][i]
        temp = temps[i]
        gust = gusts[i] if i < len(gusts) else 0
        rain = probs[i]  if i < len(probs) else 0

        if time_format == "24h":
            time_str = dt.strftime("%H:%M")
        else:
            time_str = (
                f"{str(int(dt.strftime('%I')))}:{dt.strftime('%M')} {dt.strftime('%p')}"
            ).rjust(8)

        bar_len = int(max_bar * (temp - min_t) / t_range)
        bar     = "#" * bar_len + " " * (max_bar - bar_len)

        tc = temp_color(temp)
        gc = (Fore.RED    if gust >= alert_mph        else
              Fore.YELLOW if gust >= alert_mph * 0.75 else "")

        gust_str = f" {gc}Gust:{gust:>5.1f}{Style.RESET_ALL}" if gust > 5 else ""
        rain_str = f" 🌧{rain:>3.0f}%" if rain >= 20 else ""

        print(f"{time_str} {tz} | {tc}{temp:>5.1f}°F{Style.RESET_ALL} | {bar} |{gust_str}{rain_str}")


# ── 7-day forecast ────────────────────────────────────────────────────────────

def display_forecast(forecast: list, width: int):
    w    = width
    mode = display_mode(w)
    print()

    if mode == "ultra_compact":
        # ── Ultra-compact: 3 days, single line ────────────────────────────────
        print(f"─3-Day{'─'*(w-6)}" if w > 6 else "─"*w)
        for day in forecast[:3]:
            tc_h = temp_color(day["high"])
            rc   = "🌧" if day["rain_prob"] > 40 else ""
            desc = _trunc(day["desc_short"], 8)
            print(f"{day['day_label'][:3]} {tc_h}{day['high']:.0f}{Style.RESET_ALL}/"
                  f"{day['low']:.0f}° {desc} {rc}{day['rain_prob']:.0f}%")
        return

    if mode == "compact":
        # ── Compact: 5 days, one line ──────────────────────────────────────────
        print("5-Day Forecast")
        print(separator(w))
        for day in forecast[:5]:
            tc_h = temp_color(day["high"])
            rc   = Fore.RED if day["rain_prob"] > 70 else Fore.YELLOW if day["rain_prob"] > 40 else ""
            desc = _trunc(day["desc_short"], 12)
            print(f"{day['day_label'][:3]}  {tc_h}{day['high']:.0f}/{day['low']:.0f}°F{Style.RESET_ALL}"
                  f"  {rc}🌧{day['rain_prob']:.0f}%{Style.RESET_ALL}  {desc}")
        return

    # ── Standard / Full: 7 days, two lines ────────────────────────────────────
    print("7-Day Forecast")
    print(separator(w))

    for day in forecast:
        tc_h = temp_color(day["high"])
        tc_l = temp_color(day["low"])
        rain  = day["rain_prob"]
        rc    = Fore.RED if rain > 70 else Fore.YELLOW if rain > 40 else Fore.GREEN

        desc = _trunc(day["desc_short"], w - 6)
        print(f"{day['day_label']}  {desc}")
        print(f"     High {tc_h}{day['high']:.0f}°F{Style.RESET_ALL}   "
              f"Low {tc_l}{day['low']:.0f}°F{Style.RESET_ALL}   "
              f"Rain {rc}{rain:.0f}%{Style.RESET_ALL}")
        if day.get("gust_max", 0) > 35:
            print(f"     {Fore.YELLOW}⚠ Gusts up to {day['gust_max']:.0f} mph{Style.RESET_ALL}")
        print()


# ── Rain timeline ─────────────────────────────────────────────────────────────

def display_rain_timeline(hourly: dict, width: int, time_format: str = "12h"):
    probs = hourly.get("precip_probs", [])
    w     = width
    mode  = display_mode(w)

    # Ultra-compact: only show if significant rain, 6 hours max
    threshold = 30 if mode == "ultra_compact" else 5
    hours     = 6  if mode == "ultra_compact" else 12

    if not probs or max(probs[:hours]) < threshold:
        return

    print()

    if mode == "ultra_compact":
        print(f"─Rain{'─'*(w-5)}" if w > 5 else "─"*w)
        for i in range(min(hours, len(probs))):
            if probs[i] < threshold:
                continue
            dt   = hourly["times_parsed"][i]
            rain = probs[i]
            ts   = dt.strftime("%H") if time_format == "24h" else dt.strftime("%-I%p").lower()
            rc   = Fore.RED if rain > 70 else Fore.YELLOW if rain > 40 else Fore.CYAN
            print(f"{ts} {rc}🌧{rain:.0f}%{Style.RESET_ALL}")
        return

    print("Rain Probability (Next 12 hours)")
    print(separator(w))

    bar_scale = max(1, (w - 22))   # scale bar to available width
    for i in range(min(12, len(probs))):
        dt   = hourly["times_parsed"][i]
        rain = probs[i]

        if time_format == "24h":
            time_str = dt.strftime("%H:%M")
        else:
            time_str = (
                f"{str(int(dt.strftime('%I')))}:{dt.strftime('%M')} {dt.strftime('%p')}"
            ).rjust(8)

        bar_len = max(1, int(rain / 100 * bar_scale)) if rain > 0 else 0
        bar     = "▒" * bar_len
        rc      = Fore.RED if rain > 70 else Fore.YELLOW if rain > 40 else Fore.CYAN
        print(f"{time_str} | {rc}{rain:>3.0f}%{Style.RESET_ALL} | {rc}{bar}{Style.RESET_ALL}")


# ── Regional overview ─────────────────────────────────────────────────────────

def display_regional(cities: list, width: int):
    """cities = list of (name, temp, desc) tuples."""
    w    = width
    mode = display_mode(w)
    print()
    if mode == "ultra_compact":
        print(separator(w, "─"))
        for name, temp, desc in cities:
            tc = temp_color(temp)
            print(f"{tc}{temp:>3.0f}°{Style.RESET_ALL} {_trunc(name, w - 6)}")
    else:
        print("Regional Weather Overview")
        print(separator(w))
        name_w = max(10, w - 26)
        for name, temp, desc in cities:
            tc = temp_color(temp)
            d  = _trunc(desc, max(8, w - name_w - 16))
            print(f"  {_trunc(name, name_w):<{name_w}}  {tc}{temp:>5.1f}°F{Style.RESET_ALL}  {d}")
    print()


# ── Road511 Display Functions ─────────────────────────────────────────────────

def display_route_safety(report: dict, config: dict, width: int) -> None:
    """Display the full route safety report from check_route_safety()."""
    w    = width
    mode = display_mode(w)

    print()
    if mode == "ultra_compact":
        print(separator(w, "━"))
        print(_trunc("ROUTE SAFETY", w).center(w))
        print(separator(w, "━"))
    else:
        inner = w - 4
        print("  ┌" + "─" * inner + "┐")
        label = _trunc("  ROUTE SAFETY CHECK", inner)
        print(f"  │{label:<{inner}}│")
        print("  └" + "─" * inner + "┘")

    print()

    if not report.get("available"):
        reason = report.get("reason", "unavailable")
        if reason == "no_api_key":
            print(f"  Road511 data requires a CleanShot account.")
            print(f"  Register for your free 30-day trial: cleanshot register")
            print(f"  (Existing key? cleanshot settings road511-key <key>)")
        else:
            print(f"  Road511 unavailable: {reason}")
        print()
        return

    safe = report.get("safe", True)
    if safe:
        status_color = Fore.GREEN
        status_text  = "Route appears CLEAR"
        status_icon  = "✅"
    else:
        status_color = Fore.RED
        status_text  = "HAZARDS DETECTED"
        status_icon  = "🚨"

    print(f"  {status_color}{status_icon} {status_text}{Style.RESET_ALL}")

    # Critical items
    critical = report.get("critical", [])
    if critical:
        print()
        for item in critical[:5]:
            print(f"  {Fore.RED}⚠  {_trunc(item, w - 6)}{Style.RESET_ALL}")

    # Bridge clearances
    bridge_alerts = report.get("bridge_alerts", [])
    if config.get("show_bridge_warnings", True):
        print()
        if mode != "ultra_compact":
            print(f"  Bridge Clearances")
            print("  " + separator(min(w - 4, 40), "─"))
        if bridge_alerts:
            for b in bridge_alerts[:5]:
                road = b.get("road", "Unknown road")
                clr  = b.get("clearance_ft", 0)
                line = f"  ⚠  {road} — {clr:.1f} ft clearance  LOW CLEARANCE"
                print(f"{Fore.RED}{_trunc(line, w)}{Style.RESET_ALL}")
        else:
            print(f"  {Fore.GREEN}✓  All bridges within radius: OK{Style.RESET_ALL}")

    # Active incidents
    incidents = report.get("incidents", [])
    if incidents:
        print()
        if mode != "ultra_compact":
            print(f"  Active Incidents  [DOT/511]")
            print("  " + separator(min(w - 4, 40), "─"))
        _SEV_COLOR = {"critical": Fore.RED, "high": Fore.RED,
                      "medium": Fore.YELLOW, "low": Fore.WHITE}
        for inc in incidents[:5]:
            sev  = inc.get("severity", "low")
            road = inc.get("road") or inc.get("highway") or ""
            desc = inc.get("description", "")
            col  = _SEV_COLOR.get(sev, Fore.WHITE)
            sev_tag = {"critical": "[C]", "high": "[M]",
                       "medium": "[m]", "low": "[-]"}.get(sev, "[-]")
            road_str = f" {road}" if road else ""
            line = f"  {sev_tag}{road_str} {desc}"
            print(f"  {col}{_trunc(line.strip(), w - 2)}{Style.RESET_ALL}")

    # Weigh stations
    weigh = report.get("weigh_stations", [])
    if weigh and config.get("show_weigh_stations", True):
        display_weigh_stations(weigh, w)

    # Truck parking
    parking = report.get("truck_parking", [])
    if parking and config.get("show_truck_parking", True):
        print()
        if mode != "ultra_compact":
            print(f"  Truck Parking (nearest {len(parking)})")
            print("  " + separator(min(w - 4, 40), "─"))
        for stop in parking:
            name = stop.get("name", "Truck Stop")
            road = stop.get("road", "")
            dist = stop.get("distance_miles", 0)
            road_str = f" — {road}" if road else ""
            line = f"  {_trunc(name, 30)}{road_str}  ({dist:.0f} mi)"
            print(_trunc(line, w))

    print()


def display_bridge_alerts(bridges: list, vehicle_height_ft: float,
                          width: int) -> None:
    """Standalone display for bridge clearance alerts."""
    w    = width
    mode = display_mode(w)

    print()
    if mode == "ultra_compact":
        print(separator(w, "─"))
        print(_trunc("BRIDGE CLEARANCES", w).center(w))
    else:
        print(f"  Bridge Clearances (vehicle height: {vehicle_height_ft:.1f} ft)")
        print("  " + separator(min(w - 4, 50), "─"))

    if not bridges:
        print(f"  {Fore.GREEN}✓  No bridge data available{Style.RESET_ALL}")
        print()
        return

    flagged   = [b for b in bridges if b.get("flagged")]
    ok_count  = len(bridges) - len(flagged)

    for b in flagged:
        road = b.get("road", "Unknown")
        name = b.get("name", "")
        clr  = b.get("clearance_ft", 0)
        wlim = b.get("weight_limit_tons")
        name_str = f" ({name})" if name else ""
        wlim_str = f"  Weight limit: {wlim:.0f} tons" if wlim else ""
        line1 = f"  ⚠  {road}{name_str} — {clr:.1f} ft clearance  LOW CLEARANCE"
        print(f"{Fore.RED}{_trunc(line1, w)}{Style.RESET_ALL}")
        if wlim_str and mode in ("standard", "full"):
            print(f"{Fore.YELLOW}{_trunc('     ' + wlim_str.strip(), w)}{Style.RESET_ALL}")

    if ok_count > 0:
        plural = "s" if ok_count != 1 else ""
        print(f"  {Fore.GREEN}✓  {ok_count} other bridge{plural} within radius: OK{Style.RESET_ALL}")

    print()


def display_weigh_stations(stations: list, width: int) -> None:
    """Display weigh station open/closed status with distance."""
    w    = width
    mode = display_mode(w)

    print()
    if mode != "ultra_compact":
        print(f"  Weigh Stations (next 50 mi)")
        print("  " + separator(min(w - 4, 40), "─"))

    if not stations:
        print("  No weigh station data available")
        print()
        return

    for ws in stations[:8]:
        status  = ws.get("status", "unknown").upper()
        name    = ws.get("name", "Weigh Station")
        road    = ws.get("road", "")
        dirn    = ws.get("direction", "")
        dist    = ws.get("distance_miles", 0)

        if status == "OPEN":
            sc = Fore.GREEN
        elif status == "CLOSED":
            sc = Fore.RED
        else:
            sc = Fore.YELLOW

        road_dir = ""
        if road and dirn and dirn != "unknown":
            road_dir = f"{road} {dirn.capitalize()}"
        elif road:
            road_dir = road

        dist_str = f"  ({dist:.0f} mi)" if dist else ""
        if mode == "ultra_compact":
            line = f"{status[:1]} {_trunc(name, w - 8)}{dist_str}"
        else:
            line = f"  {sc}{status:<6}{Style.RESET_ALL}  {_trunc(name, 28)}"
            if road_dir:
                line += f" — {_trunc(road_dir, 16)}"
            line += dist_str

        print(_trunc(line, w))

    print()
