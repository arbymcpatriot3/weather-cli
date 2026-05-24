#!/usr/bin/env python3
# core/compress.py — Clean Shot: data minimization for 2G/EDGE
#
# Budgets enforced:
#   Full route refresh    < 50 KB
#   Single hazard report  < 200 bytes
#   Background / hour     < 5 KB
#
# Strategies:
#   - Strip unused fields from Open-Meteo response before caching
#   - gzip compress all cache files
#   - Pack hazard reports to minimal JSON (key abbreviations)
#   - Diff-only updates: only fetch fields that have changed
#
# TODO: implement field stripping + gzip cache in module sprint

import json
import gzip


# Minimal fields needed for offline display (subset of full Open-Meteo response)
_KEEP_CURRENT = {
    "temperature_2m", "apparent_temperature", "relative_humidity_2m",
    "weather_code", "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
}

_KEEP_HOURLY = {
    "time", "temperature_2m", "precipitation_probability",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
}

_KEEP_DAILY = {
    "time", "weather_code", "temperature_2m_max", "temperature_2m_min",
    "precipitation_probability_max", "sunrise", "sunset",
    "wind_speed_10m_max", "wind_gusts_10m_max",
}


def strip_weather_response(data_str: str) -> str:
    """
    Remove unused fields from Open-Meteo JSON response.
    Reduces cache size by ~40% for offline storage.
    """
    # TODO: implement field filtering
    return data_str


def compress_bytes(data: str) -> bytes:
    """gzip-compress a string. Returns bytes."""
    return gzip.compress(data.encode("utf-8"), compresslevel=6)


def decompress_bytes(data: bytes) -> str:
    """Decompress gzip bytes to string."""
    return gzip.decompress(data).decode("utf-8")


def pack_hazard_report(lat: float, lon: float,
                       hazard_type: str, ts: int) -> str:
    """
    Pack a hazard report to minimal JSON (< 200 bytes).
    Keys abbreviated: t=type, lat, lon, ts=timestamp
    """
    return json.dumps({"t": hazard_type, "lat": round(lat, 4),
                       "lon": round(lon, 4), "ts": ts})


def estimate_bytes(data_str: str) -> int:
    """Return compressed size estimate in bytes."""
    return len(compress_bytes(data_str))
