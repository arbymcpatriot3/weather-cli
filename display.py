#!/usr/bin/env python3
# display.py - All display/output functions

import shutil
import sys
from colorama import Fore, Style, init
from parse import degrees_to_dir

init(autoreset=True)


# ── Terminal helpers ───────────────────────────────────────────────────────────

def get_width() -> int:
    return min(shutil.get_terminal_size(fallback=(80, 24)).columns, 80)


def separator(width: int, char: str = "-") -> str:
    return char * 78


def print_header(title: str, width: int, version: str = ""):
    """Print a boxed header, capped at 80 columns."""
    w = min(width, 80)
    ver = f"  v{version}" if version else ""
    full_title = f"  {title}{ver}  "
    # Truncate title if too long
    if len(full_title) > w - 2:
        full_title = full_title[:w - 5] + "...  "
    bar = "─" * (w - 2)
    pad = max(0, w - 2 - len(full_title))
    print(f"┌{bar}┐")
    print(f"│{full_title}{' ' * pad}│")
    print(f"└{bar}┘")
    print()


# ── Temperature color ─────────────────────────────────────────────────────────

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


# ── Compact 80-column ────────────────────────────────────────────────────────

def display_compact(parsed: dict, width: int):
    cur  = parsed["current"]
    fc   = parsed["forecast"][0]  # today
    city = parsed["city"]
    w    = min(width, 80)

    print("-" * w)
    print(f"  {city}".center(w))
    print("-" * w)
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
    w     = min(width, 80)

    cache_age = parsed.get("cache_age", 0)
    cache_str = f"  (cached, {cache_age} min old)" if cache_age > 0 else ""
    print(f"Location: {city}")
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
    w = min(width, 80)
    print()
    print(f"{Fore.RED}{'─'*w}{Style.RESET_ALL}")
    print(f"{Fore.RED}⚠  ACTIVE WEATHER ALERTS{Style.RESET_ALL}")
    print(f"{Fore.RED}{'─'*w}{Style.RESET_ALL}")
    for a in alerts:
        sev = a.get("severity", "")
        color = Fore.RED if sev == "Extreme" else Fore.YELLOW if sev == "Severe" else Fore.WHITE
        print(f"{color}• {a['event']}{Style.RESET_ALL}")
        if a.get("headline"):
            # Wrap headline to width
            headline = a["headline"]
            if len(headline) > w - 4:
                headline = headline[:w - 7] + "..."
            print(f"  {headline}")
    print(f"{Fore.RED}{'─'*w}{Style.RESET_ALL}")


# ── Wind alert for truckers ───────────────────────────────────────────────────

def display_wind_alert(hourly: dict, alert_mph: float, width: int):
    gusts = hourly.get("wind_gusts", [0] * 24)
    if not gusts:
        return
    max_gust = max(gusts)
    if max_gust >= alert_mph:
        w = min(width, 80)
        print()
        print(f"{Fore.RED}⚠  TRUCKER WIND ALERT: Gusts up to {max_gust:.1f} mph in next 24h{Style.RESET_ALL}")
        print(f"{Fore.RED}   Secure all loads! High-profile vehicle caution advised.{Style.RESET_ALL}")


# ── Hourly chart ──────────────────────────────────────────────────────────────

def display_hourly(hourly: dict, width: int, time_format: str = "12h",
                   alert_mph: float = 40):
    w = min(width, 80)
    print()
    print("Hourly Forecast (Next 24 hours)")
    print(separator(w))

    temps  = hourly["temps"]
    gusts  = hourly.get("wind_gusts", [0] * 24)
    probs  = hourly.get("precip_probs", [0] * 24)
    tz     = hourly.get("tz_label", "")

    max_t = max(temps) if temps else 100
    min_t = min(temps) if temps else 0
    t_range = max_t - min_t if max_t != min_t else 1

    for i in range(24):
        dt    = hourly["times_parsed"][i]
        temp  = temps[i]
        gust  = gusts[i]
        rain  = probs[i]

        # Time string
        if time_format == "24h":
            time_str = dt.strftime("%H:%M")
        else:
            time_str = dt.strftime("%-I:%M %p").rjust(8)

        # Temperature bar (20 chars wide)
        bar_len = int(20 * (temp - min_t) / t_range)
        bar     = "#" * bar_len + " " * (20 - bar_len)

        # Colors
        tc = temp_color(temp)
        gc = Fore.RED if gust >= alert_mph else Fore.YELLOW if gust >= alert_mph * 0.75 else ""

        # Gust marker - consistent width
        if gust > 5:
            gust_str = f" {gc}Gust:{gust:>5.1f}{Style.RESET_ALL}"
        else:
            gust_str = ""

        # Rain marker
        rain_str = f" 🌧{rain:>3.0f}%" if rain >= 20 else ""

        print(f"{time_str} {tz} | {tc}{temp:>5.1f}°F{Style.RESET_ALL} | {bar} |{gust_str}{rain_str}")


# ── 7-day forecast ────────────────────────────────────────────────────────────

def display_forecast(forecast: list, width: int):
    w = min(width, 80)
    print()
    print("7-Day Forecast")
    print(separator(w))

    for day in forecast:
        tc_h = temp_color(day["high"])
        tc_l = temp_color(day["low"])
        rain  = day["rain_prob"]
        rc    = Fore.RED if rain > 70 else Fore.YELLOW if rain > 40 else Fore.GREEN

        print(f"{day['day_label']}  {day['desc_short']}")
        print(f"     High {tc_h}{day['high']:.0f}°F{Style.RESET_ALL}   "
              f"Low {tc_l}{day['low']:.0f}°F{Style.RESET_ALL}   "
              f"Rain {rc}{rain:.0f}%{Style.RESET_ALL}")
        if day.get("gust_max", 0) > 35:
            print(f"     {Fore.YELLOW}⚠ Gusts up to {day['gust_max']:.0f} mph{Style.RESET_ALL}")
        print()


# ── Rain timeline (next 12h) ──────────────────────────────────────────────────

def display_rain_timeline(hourly: dict, width: int, time_format: str = "12h"):
    probs = hourly.get("precip_probs", [])
    # Skip entirely if no meaningful rain chance in next 12h
    if not probs or max(probs[:12]) < 5:
        return

    w = min(width, 80)
    print()
    print("Rain Probability (Next 12 hours)")
    print(separator(w))

    for i in range(12):
        dt   = hourly["times_parsed"][i]
        rain = probs[i]

        if time_format == "24h":
            time_str = dt.strftime("%H:%M")
        else:
            time_str = dt.strftime("%-I:%M %p").rjust(8)

        bar_len = max(1, int(rain / 5)) if rain > 0 else 0
        bar     = "▒" * bar_len
        rc      = Fore.RED if rain > 70 else Fore.YELLOW if rain > 40 else Fore.CYAN
        print(f"{time_str} | {rc}{rain:>3.0f}%{Style.RESET_ALL} | {rc}{bar}{Style.RESET_ALL}")


# ── Regional weather map ──────────────────────────────────────────────────────

def display_regional(cities: list, width: int):
    """Display weather for a list of cities. cities = list of (name, temp, desc) tuples."""
    w = min(width, 80)
    print()
    print("Regional Weather Overview")
    print(separator(w))
    for name, temp, desc in cities:
        tc = temp_color(temp)
        print(f"  {name:<16}  {tc}{temp:>5.1f}°F{Style.RESET_ALL}  {desc}")
    print()


# ── Route display ─────────────────────────────────────────────────────────────

def display_route_header(start: str, end: str, stops: int):
    print()
    print(f"Route Weather: {start}  →  {end}")
    print(f"({stops} stops along route)")
    print()


def display_route_stop(stop_num: int, city: str, parsed: dict,
                       alert_mph: float, width: int):
    w = min(width, 80)
    cur = parsed["current"]
    fc  = parsed["forecast"][0]
    print(f"{'─'*w}")
    print(f"Stop {stop_num}: {city}")
    print(f"{'─'*w}")

    tc = temp_color(cur["temp"])
    wc = wind_color(cur["wind_speed"], alert_mph)
    print(f"  Temp  : {tc}{cur['temp']:.1f}°F{Style.RESET_ALL}  "
          f"(feels {cur['feels']:.1f}°F)  {cur['desc_short']}")
    print(f"  Wind  : {wc}{cur['wind_speed']:.1f} mph{Style.RESET_ALL}  "
          f"{degrees_to_dir(cur['wind_dir'])}")
    if cur["wind_gust"] > alert_mph:
        print(f"  {Fore.RED}⚠ GUST ALERT: {cur['wind_gust']:.1f} mph{Style.RESET_ALL}")
    print(f"  Today : High {fc['high']:.0f}°  Low {fc['low']:.0f}°  "
          f"Rain {fc['rain_prob']:.0f}%")
    print()
