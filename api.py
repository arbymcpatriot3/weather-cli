#!/usr/bin/env python3
# api.py - API fetching, geocoding, caching, alerts

import requests
import json
import hashlib
import sys
from pathlib import Path
from datetime import datetime

CACHE_DIR  = Path("/tmp") / "weather-cli-cache"
CACHE_TIME = 600  # 10 minutes
ALERT_CACHE_TIME = 300  # 5 minutes - alerts refresh faster


def _cache_path(lat: float, lon: float, suffix: str = "") -> Path:
    """Generate a unique cache file path per location."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{lat:.4f},{lon:.4f}{suffix}".encode()).hexdigest()[:16]
    return CACHE_DIR / f"weather_{key}{suffix}.json"


def _cache_load(path: Path, max_age: int):
    """Load cache if it exists and is fresh. Returns (data_str, age_minutes) or (None, None)."""
    if not path.exists():
        return None, None
    now = datetime.now()
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    age_sec = (now - mtime).total_seconds()
    if age_sec < max_age:
        return path.read_text(), int(age_sec // 60)
    return None, None


def _cache_save(path: Path, data: str):
    """Write data to cache file atomically."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data)
    tmp.rename(path)


def fetch_weather(lat: float, lon: float, force_fresh: bool = False):
    """
    Fetch weather from Open-Meteo. Returns (data_str, cache_age_minutes).
    cache_age_minutes = 0 means fresh from API.
    Returns (None, None) on failure.
    """
    path = _cache_path(lat, lon)

    if not force_fresh:
        data, age = _cache_load(path, CACHE_TIME)
        if data:
            return data, age

    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
        "weather_code,wind_speed_10m,wind_direction_10m,wind_gusts_10m"
        "&hourly=temperature_2m,precipitation_probability,"
        "wind_speed_10m,wind_direction_10m,wind_gusts_10m,uv_index"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max,sunrise,sunset,wind_speed_10m_max,"
        "wind_gusts_10m_max"
        "&temperature_unit=fahrenheit&windspeed_unit=mph"
        "&precipitation_unit=inch&timezone=auto&forecast_days=7"
    )

    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.text
        _cache_save(path, data)
        return data, 0
    except requests.RequestException as e:
        print(f"⚠  API error: {e}", file=sys.stderr)
        # Fall back to stale cache if available
        if path.exists():
            age_sec = (datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)).total_seconds()
            age_min = int(age_sec // 60)
            print(f"   Using cached data ({age_min} min old)", file=sys.stderr)
            return path.read_text(), age_min
        return None, None


def fetch_alerts(lat: float, lon: float):
    """
    Fetch active NWS weather alerts for a US location.
    Returns list of alert dicts with 'event', 'headline', 'severity'.
    Returns [] on failure or no alerts.
    """
    path = _cache_path(lat, lon, "_alerts")

    cached, age = _cache_load(path, ALERT_CACHE_TIME)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    try:
        url = f"https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}"
        headers = {"User-Agent": "weather-cli/2.0 (arbymcpatriot@proton.me)"}
        r = requests.get(url, timeout=8, headers=headers)
        r.raise_for_status()
        features = r.json().get("features", [])
        alerts = []
        for f in features:
            props = f.get("properties", {})
            alerts.append({
                "event":    props.get("event", "Unknown"),
                "headline": props.get("headline", ""),
                "severity": props.get("severity", "Unknown"),
                "urgency":  props.get("urgency", "Unknown"),
            })
        _cache_save(path, json.dumps(alerts))
        return alerts
    except Exception:
        return []


def geocode_location(location_str: str):
    """
    Geocode a city name, ZIP code, or 'city state' string to lat/lon.
    Returns (lat, lon, city_name) or (None, None, None) on failure.
    """
    location_str = location_str.strip()

    # Handle "lat,lon" direct input
    if "," in location_str:
        parts = location_str.split(",")
        if len(parts) == 2:
            try:
                lat, lon = float(parts[0]), float(parts[1])
                return lat, lon, f"({lat:.4f}, {lon:.4f})"
            except ValueError:
                pass

    # Build list of queries to try in order
    queries = []

    # Format "City ST" — try city name alone first (Open-Meteo handles it better)
    if " " in location_str and not location_str.replace(" ", "").isdigit():
        parts = location_str.rsplit(" ", 1)
        if len(parts[1]) == 2 and parts[1].isalpha():
            city_only = parts[0]
            queries.append(city_only)          # e.g. "Pennsville"
    queries.append(location_str)               # original as-is e.g. "08079"

    for query in queries:
        url = (
            f"https://geocoding-api.open-meteo.com/v1/search"
            f"?name={requests.utils.quote(query)}&count=5&language=en"
        )
        try:
            r = requests.get(url, timeout=8)
            r.raise_for_status()
            results = r.json().get("results", [])
            if results:
                # If we searched city-only and have a state hint, prefer matching state
                state_hint = None
                if " " in location_str and not location_str.replace(" ", "").isdigit():
                    parts = location_str.rsplit(" ", 1)
                    if len(parts[1]) == 2 and parts[1].isalpha():
                        state_hint = parts[1].upper()

                res = results[0]  # default to first result
                if state_hint and len(results) > 1:
                    for candidate in results:
                        admin = candidate.get("admin1_code", "") or candidate.get("admin1", "")
                        # Match state abbreviation
                        if state_hint in (admin or "").upper():
                            res = candidate
                            break

                name = res["name"]
                admin = res.get("admin1", "")
                country = res.get("country_code", "")
                if admin and country == "US":
                    name = f"{name}, {admin}"
                elif country and country != "US":
                    name = f"{name}, {country}"
                return res["latitude"], res["longitude"], name
        except Exception as e:
            print(f"⚠  Geocode error: {e}", file=sys.stderr)
            continue

    print(f"⚠  No results found for '{location_str}'", file=sys.stderr)
    return None, None, None


def get_auto_location():
    """
    Auto-detect location via IP geolocation (~1KB request, no key needed).
    Returns (lat, lon, city) or (None, None, None).
    """
    try:
        r = requests.get("https://ipapi.co/json/", timeout=5)
        if r.status_code == 200:
            d = r.json()
            lat  = d.get("latitude")
            lon  = d.get("longitude")
            city = d.get("city", "Unknown")
            region = d.get("region_code", "")
            if city and region:
                city = f"{city}, {region}"
            return lat, lon, city
    except Exception:
        pass
    return None, None, None
