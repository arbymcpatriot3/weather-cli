#!/usr/bin/env python3
# core/parse.py — Clean Shot: parse Open-Meteo API response into clean dicts
# Migrated from parse.py v2.0.0 — no behavioral changes.

import json
from datetime import datetime


# ── Weather code table ────────────────────────────────────────────────────────

WEATHER_CODES = {
    0:  ("Clear sky",              "☀"),
    1:  ("Mainly clear",           "🌤"),
    2:  ("Partly cloudy",          "⛅"),
    3:  ("Overcast",               "☁"),
    45: ("Fog",                    "🌫"),
    48: ("Icy fog",                "🌫"),
    51: ("Light drizzle",          "🌦"),
    53: ("Drizzle",                "🌦"),
    55: ("Heavy drizzle",          "🌧"),
    56: ("Freezing drizzle",       "🌨"),
    57: ("Heavy freezing drizzle", "🌨"),
    61: ("Slight rain",            "🌧"),
    63: ("Rain",                   "🌧"),
    65: ("Heavy rain",             "🌧"),
    66: ("Freezing rain",          "🌧❄"),
    67: ("Heavy freezing rain",    "🌧❄"),
    71: ("Slight snow",            "❄"),
    73: ("Snow",                   "❄"),
    75: ("Heavy snow",             "❄"),
    77: ("Snow grains",            "❄"),
    80: ("Rain showers",           "🚿"),
    81: ("Moderate showers",       "🚿"),
    82: ("Violent showers",        "🚿"),
    85: ("Snow showers",           "❄🚿"),
    86: ("Heavy snow showers",     "❄🚿"),
    95: ("Thunderstorm",           "⛈"),
    96: ("Thunderstorm w/ hail",   "⛈"),
    99: ("Thunderstorm w/ hail",   "⛈"),
}


def weather_desc(code: int) -> str:
    desc, emoji = WEATHER_CODES.get(code, (f"Unknown ({code})", "?"))
    return f"{desc:<22} {emoji}"


def weather_desc_short(code: int) -> str:
    desc, emoji = WEATHER_CODES.get(code, (f"Unknown ({code})", "?"))
    return f"{desc} {emoji}"


# ── Direction helpers ──────────────────────────────────────────────────────────

_DIRS   = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
           "S","SSW","SW","WSW","W","WNW","NW","NNW"]
_ARROWS = ["↑","↗","↗","↗","→","↘","↘","↘",
           "↓","↙","↙","↙","←","↖","↖","↖"]


def degrees_to_dir(deg) -> str:
    """Convert wind degrees to cardinal direction + arrow. Safe for None/0."""
    if deg is None:
        return "---"
    try:
        deg = float(deg) % 360
        if deg < 0:
            deg += 360
        idx = round(deg / 22.5) % 16
        return f"{_DIRS[idx]} {_ARROWS[idx]}"
    except (ValueError, TypeError):
        return "---"


# ── Timezone display ───────────────────────────────────────────────────────────

def tz_display(tz_abbr: str, timezone: str, month: int) -> str:
    """Convert raw timezone abbreviation to friendly display string."""
    dst = 3 <= month <= 11
    mapping = {
        "GMT-4": "EDT" if dst else "EST",
        "GMT-5": "CDT" if dst else "EST",
        "GMT-6": "CST" if dst else "CST",
        "GMT-7": "MDT" if dst else "MST",
        "GMT-8": "PDT" if dst else "PST",
        "GMT-9": "PST",
    }
    if tz_abbr in mapping:
        return mapping[tz_abbr]
    if tz_abbr and len(tz_abbr) <= 5:
        return tz_abbr
    if timezone and "/" in timezone:
        return timezone.split("/")[-1].replace("_", " ")[:10]
    return "Local"


def _fmt_time(iso_str: str) -> str:
    """Extract HH:MM from ISO datetime string."""
    try:
        return iso_str.split("T")[1][:5]
    except Exception:
        return iso_str


# ── Main parse functions ───────────────────────────────────────────────────────

def parse_current(data_str: str) -> dict:
    """Parse current conditions block from Open-Meteo response."""
    d = json.loads(data_str)
    c = d["current"]
    return {
        "temp":       c["temperature_2m"],
        "feels":      c["apparent_temperature"],
        "humidity":   c["relative_humidity_2m"],
        "wind_speed": c["wind_speed_10m"],
        "wind_dir":   c.get("wind_direction_10m", 0),
        "wind_gust":  c.get("wind_gusts_10m", 0),
        "code":       c["weather_code"],
        "desc":       weather_desc(c["weather_code"]),
        "desc_short": weather_desc_short(c["weather_code"]),
    }


def parse_forecast(data_str: str) -> list:
    """Parse 7-day forecast. Returns list of day dicts."""
    d = json.loads(data_str)
    daily = d["daily"]
    days = []
    for i in range(len(daily["time"])):
        date_str = daily["time"][i]
        try:
            date_obj  = datetime.strptime(date_str, "%Y-%m-%d")
            day_label = date_obj.strftime("%a %b %d")
        except Exception:
            day_label = date_str
        days.append({
            "date":       date_str,
            "day_label":  day_label,
            "code":       daily["weather_code"][i],
            "desc":       weather_desc(daily["weather_code"][i]),
            "desc_short": weather_desc_short(daily["weather_code"][i]),
            "high":       daily["temperature_2m_max"][i],
            "low":        daily["temperature_2m_min"][i],
            "rain_prob":  daily["precipitation_probability_max"][i],
            "sunrise":    _fmt_time(daily["sunrise"][i]),
            "sunset":     _fmt_time(daily["sunset"][i]),
            "wind_max":   daily.get("wind_speed_10m_max", [0]*7)[i],
            "gust_max":   daily.get("wind_gusts_10m_max", [0]*7)[i],
        })
    return days


def parse_hourly(data_str: str) -> dict:
    """Parse 24-hour hourly data from Open-Meteo response, starting from current hour."""
    d = json.loads(data_str)
    hourly   = d["hourly"]
    timezone = d.get("timezone", "")
    tz_abbr  = d.get("timezone_abbreviation", "")
    now      = datetime.now()
    tz_label = tz_display(tz_abbr, timezone, now.month)

    all_times = hourly.get("time", [])
    # Find index of current hour — show 24h starting from now, not from midnight.
    # Use datetime comparison (not string) for reliability across timezones.
    current_dt = now.replace(minute=0, second=0, microsecond=0)
    start_idx = 0
    for i, t in enumerate(all_times):
        try:
            if datetime.fromisoformat(t) >= current_dt:
                start_idx = i
                break
        except Exception:
            continue

    def _slice(key, default=0):
        vals = hourly.get(key, [default] * (len(all_times) or 168))
        return vals[start_idx:start_idx + 24]

    times_iso    = all_times[start_idx:start_idx + 24]
    times_parsed = [datetime.fromisoformat(t) for t in times_iso]

    return {
        "times_iso":    times_iso,
        "times_parsed": times_parsed,
        "tz_label":     tz_label,
        "temps":        _slice("temperature_2m"),
        "precip_probs": _slice("precipitation_probability"),
        "wind_speeds":  _slice("wind_speed_10m"),
        "wind_dirs":    _slice("wind_direction_10m"),
        "wind_gusts":   _slice("wind_gusts_10m"),
        "uv_indices":   _slice("uv_index"),
    }
