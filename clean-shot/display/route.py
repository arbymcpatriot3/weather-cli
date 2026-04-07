#!/usr/bin/env python3
# display/route.py — Clean Shot: route weather display
# Migrated from display.py v2.0.0 (route functions only)

from colorama import Fore, Style, init
from core.parse import degrees_to_dir
from display.full import temp_color, wind_color, separator

init(autoreset=True)


def display_route_header(start: str, end: str, stops: int):
    print()
    print(f"Route Weather: {start}  →  {end}")
    print(f"({stops} stops along route)")
    print()


def display_route_stop(stop_num: int, city: str, parsed: dict,
                       alert_mph: float, width: int):
    w   = min(width, 80)
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
