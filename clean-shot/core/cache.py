#!/usr/bin/env python3
# core/cache.py — Clean Shot: file-based API response cache
# Design: atomic writes, stale-fallback on network loss, 2G-friendly budgets
#
# Data budgets enforced here:
#   Full route refresh  < 50 KB
#   Background / hr     < 5 KB
#   Single hazard       < 200 bytes

import hashlib
import tempfile
from pathlib import Path
from datetime import datetime

CACHE_DIR         = Path(tempfile.gettempdir()) / "clean-shot-cache"
CACHE_TIME        = 600    # 10 min — weather data
ALERT_CACHE_TIME  = 300    # 5 min  — NOAA alerts refresh faster
HAZARD_CACHE_TIME = 120    # 2 min  — community hazard reports
DOT511_CACHE_TIME = 900    # 15 min — DOT/511 feeds (slow-changing)
BRIDGE_CACHE_TIME = 86400  # 24h   — bridge clearances rarely change
TRUCK_ROUTE_CACHE = 3600   # 1h    — truck routing
CAMERA_CACHE_TIME = 120    # 2min  — cameras are near-live
FEATURE_CACHE_TIME = 900   # 15min — weigh stations, parking features


# ── Internal ──────────────────────────────────────────────────────────────────

def _cache_path(lat: float, lon: float, suffix: str = "") -> Path:
    """Unique path per location + data type. Creates cache dir if needed."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{lat:.4f},{lon:.4f}{suffix}".encode()).hexdigest()[:16]
    return CACHE_DIR / f"cs_{key}{suffix}.json"


# ── Public API ─────────────────────────────────────────────────────────────────

def cache_load(path: Path, max_age: int):
    """Load cache if it exists and is fresh.
    Returns (data_str, age_minutes) or (None, None)."""
    if not path.exists():
        return None, None
    age_sec = (datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)).total_seconds()
    if age_sec < max_age:
        return path.read_text(), int(age_sec // 60)
    return None, None


def cache_save(path: Path, data: str):
    """Write data atomically (tmp → replace) to avoid partial reads."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)   # replace() overwrites atomically on both Windows and POSIX


def cache_stale(path: Path):
    """Return stale cache regardless of age — used as network fallback.
    Returns (data_str, age_minutes) or (None, None)."""
    if path.exists():
        age_sec = (datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)).total_seconds()
        return path.read_text(), int(age_sec // 60)
    return None, None


# ── Named path helpers ────────────────────────────────────────────────────────

def weather_cache_path(lat: float, lon: float) -> Path:
    return _cache_path(lat, lon)

def alert_cache_path(lat: float, lon: float) -> Path:
    return _cache_path(lat, lon, "_alerts")

def hazard_cache_path(lat: float, lon: float) -> Path:
    return _cache_path(lat, lon, "_hazards")

def dot511_cache_path(lat: float, lon: float) -> Path:
    return _cache_path(lat, lon, "_dot511")

def parking_cache_path(lat: float, lon: float) -> Path:
    return _cache_path(lat, lon, "_parking")

def bridge_cache_path(lat: float, lon: float) -> Path:
    return _cache_path(lat, lon, "_bridges")

def route_cache_path(origin_lat: float, origin_lon: float,
                     dest_lat: float, dest_lon: float) -> Path:
    key = hashlib.sha256(
        f"{origin_lat:.3f},{origin_lon:.3f},{dest_lat:.3f},{dest_lon:.3f}".encode()
    ).hexdigest()[:16]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"cs_{key}_route.json"

def feature_cache_path(lat: float, lon: float, ftype: str) -> Path:
    return _cache_path(lat, lon, f"_{ftype}")
