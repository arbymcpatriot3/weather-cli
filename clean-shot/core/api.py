#!/usr/bin/env python3
# core/api.py — Clean Shot: Open-Meteo weather, NWS alerts, geocoding
# Data budget: weather payload ~8-12 KB gzipped; alerts ~2-4 KB
# Timeout tuned so cold start stays under 2 seconds on good signal.

import requests
import json
import sys

from core.cache import (
    cache_load, cache_save, cache_stale,
    weather_cache_path, alert_cache_path,
    CACHE_TIME, ALERT_CACHE_TIME,
)

_HEADERS = {"User-Agent": "clean-shot/3.0 (bluecollarnation@proton.me)"}


# ── Weather ───────────────────────────────────────────────────────────────────

def fetch_weather(lat: float, lon: float, force_fresh: bool = False):
    """
    Fetch weather from Open-Meteo.
    Returns (data_str, cache_age_minutes).  cache_age == 0 → fresh from API.
    Falls back to stale cache on network failure.
    Returns (None, None) only if no data exists anywhere.
    """
    path = weather_cache_path(lat, lon)

    if not force_fresh:
        data, age = cache_load(path, CACHE_TIME)
        if data:
            return data, age

    url = (
        "https://api.open-meteo.com/v1/forecast"
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
        r = requests.get(url, timeout=10, headers=_HEADERS)
        r.raise_for_status()
        data = r.text
        cache_save(path, data)
        return data, 0
    except requests.RequestException as e:
        print(f"⚠  API error: {e}", file=sys.stderr)
        data, age = cache_stale(path)
        if data:
            print(f"   Using cached data ({age} min old)", file=sys.stderr)
            return data, age
        return None, None


# ── NOAA Alerts ───────────────────────────────────────────────────────────────

def fetch_alerts(lat: float, lon: float) -> list:
    """
    Fetch active NWS weather alerts for a US location.
    Returns list of alert dicts with event/headline/severity/urgency keys.
    Returns [] on failure or no alerts.
    """
    path = alert_cache_path(lat, lon)

    cached, _ = cache_load(path, ALERT_CACHE_TIME)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    try:
        url = f"https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}"
        r = requests.get(url, timeout=8, headers=_HEADERS)
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
        cache_save(path, json.dumps(alerts))
        return alerts
    except Exception:
        return []


# ── Geocoding ─────────────────────────────────────────────────────────────────

def geocode_location(location_str: str):
    """
    Geocode a city name, ZIP code, or 'City ST' string to lat/lon.
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

    queries = []
    # "City ST" — try city name alone first (Open-Meteo handles it better)
    if " " in location_str and not location_str.replace(" ", "").isdigit():
        parts = location_str.rsplit(" ", 1)
        if len(parts[1]) == 2 and parts[1].isalpha():
            queries.append(parts[0])
    queries.append(location_str)

    for query in queries:
        url = (
            "https://geocoding-api.open-meteo.com/v1/search"
            f"?name={requests.utils.quote(query)}&count=5&language=en"
        )
        try:
            r = requests.get(url, timeout=8, headers=_HEADERS)
            r.raise_for_status()
            results = r.json().get("results", [])
            if results:
                state_hint = None
                if " " in location_str and not location_str.replace(" ", "").isdigit():
                    parts = location_str.rsplit(" ", 1)
                    if len(parts[1]) == 2 and parts[1].isalpha():
                        state_hint = parts[1].upper()

                res = results[0]
                if state_hint and len(results) > 1:
                    for candidate in results:
                        admin = candidate.get("admin1_code", "") or candidate.get("admin1", "")
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


# ── IP Auto-location ──────────────────────────────────────────────────────────

def get_auto_location():
    """
    Auto-detect location via IP geolocation (~1 KB, no API key).
    Returns (lat, lon, city) or (None, None, None).
    """
    try:
        r = requests.get("https://ipapi.co/json/", timeout=5, headers=_HEADERS)
        if r.status_code == 200:
            d = r.json()
            lat    = d.get("latitude")
            lon    = d.get("longitude")
            city   = d.get("city", "Unknown")
            region = d.get("region_code", "")
            if city and region:
                city = f"{city}, {region}"
            return lat, lon, city
    except Exception:
        pass
    return None, None, None
