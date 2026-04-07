#!/usr/bin/env python3
# core/gps.py — Clean Shot: GPS dispatcher + smart polling + location intelligence
#
# Responsibilities:
#   • Platform dispatch (Linux gpsd / Windows Location API / iOS CoreLocation)
#   • GpsResult: standardized position dict with stale flag + source
#   • Haversine distance calculation (no external libs)
#   • Motion detection: 100m delta → driving vs parked
#   • Smart polling: 60s driving, 10 min parked (battery budget)
#   • Reverse geocode: lat/lon → highway + direction + city (Nominatim, no key)
#   • Language-aware location descriptions via core/i18n
#   • Geo-confirmation: reject hazard reports > 2 miles from driver
#   • is_driving flag for HOS guardian
#   • Offline fallback: last known position from config, stale=True
#
# Zero new API keys.  Nominatim (OpenStreetMap) is free, no registration.
# Nominatim rate limit: 1 req/s — we cache results by 0.01° grid (~1 km).

import json
import math
import platform
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import requests

from core.cache import CACHE_DIR
from core.i18n.translator import t, set_language

# ── Constants ─────────────────────────────────────────────────────────────────

_EARTH_RADIUS_MI    = 3958.8

POLL_DRIVING_SEC    = 60       # 1 minute while moving
POLL_PARKED_SEC     = 600      # 10 minutes while parked
MOTION_THRESHOLD_MI = 0.0621   # 100 metres in miles — movement threshold
HAZARD_CONFIRM_MI   = 2.0      # max distance to confirm a community hazard report

_NOMINATIM_URL   = "https://nominatim.openstreetmap.org/reverse"
_NOMINATIM_HDR   = {"User-Agent": "clean-shot/3.0 (bluecollarnation@proton.me)"}
_GEOCACHE_GRID   = 0.01        # degrees — round coords for cache key (~1.1 km)
_GEOCACHE_TTL    = 300         # seconds (5 min) — driver is moving

_SOURCES = ("gps", "ip", "config")


# ── GpsResult ─────────────────────────────────────────────────────────────────

def _result(lat: float, lon: float, source: str,
            accuracy_m: float = None, stale: bool = False) -> dict:
    """Build a standardized GPS result dict."""
    return {
        "lat":        lat,
        "lon":        lon,
        "accuracy_m": accuracy_m,
        "stale":      stale,
        "source":     source,
        "timestamp":  datetime.now().isoformat(timespec="seconds"),
    }


# ── Geometry ──────────────────────────────────────────────────────────────────

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in miles."""
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ     = math.radians(lat2 - lat1)
    Δλ     = math.radians(lon2 - lon1)
    a = (math.sin(Δφ / 2) ** 2
         + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2)
    return _EARTH_RADIUS_MI * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Initial bearing from point 1 → point 2, in degrees (0 = North, clockwise).
    Returns 0.0 if points are identical.
    """
    if lat1 == lat2 and lon1 == lon2:
        return 0.0
    φ1 = math.radians(lat1)
    φ2 = math.radians(lat2)
    Δλ = math.radians(lon2 - lon1)
    x  = math.sin(Δλ) * math.cos(φ2)
    y  = math.cos(φ1) * math.sin(φ2) - math.sin(φ1) * math.cos(φ2) * math.cos(Δλ)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def bearing_to_cardinal(deg: float) -> str:
    """Convert bearing degrees to 8-point cardinal code (N/NE/E/SE/S/SW/W/NW)."""
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[round(deg / 45) % 8]


# ── Motion detection ──────────────────────────────────────────────────────────

def is_moving(old: dict, new: dict) -> bool:
    """
    Return True if the driver has moved more than MOTION_THRESHOLD_MI (100 m)
    between two GpsResult dicts.
    """
    try:
        return haversine(old["lat"], old["lon"],
                         new["lat"], new["lon"]) > MOTION_THRESHOLD_MI
    except (KeyError, TypeError):
        return False


def get_poll_interval(config: dict) -> int:
    """
    Return polling interval in seconds based on motion state.
    60s when driving, 600s (10 min) when parked.
    """
    return POLL_DRIVING_SEC if config.get("is_driving", False) else POLL_PARKED_SEC


# ── Platform dispatch ─────────────────────────────────────────────────────────

def _platform_gps() -> dict | None:
    """
    Try to get a live GPS fix from the platform driver.
    Returns GpsResult or None if unavailable.
    """
    plat = platform.system().lower()
    try:
        if plat == "linux":
            from platforms.linux.gps_linux import get_gps_linux
            pos = get_gps_linux()
            if pos:
                lat, lon = pos
                return _result(lat, lon, "gps")
        elif plat == "windows":
            from platforms.windows.gps_windows import get_gps_windows
            pos = get_gps_windows()
            if pos:
                lat, lon = pos
                return _result(lat, lon, "gps")
        elif plat == "darwin":
            # iOS / macOS — CoreLocation bridge
            from platforms.ios.gps_ios import get_gps_ios
            pos = get_gps_ios()
            if pos:
                lat, lon = pos
                return _result(lat, lon, "gps")
    except Exception:
        pass
    return None


def get_position(config: dict) -> dict | None:
    """
    Get current GPS position.

    Priority:
      1. Live GPS from platform driver
      2. Last known position from config (stale=True)
      3. None — caller must handle

    Returns a GpsResult dict or None.
    """
    # Try live GPS first (unless offline mode)
    if not config.get("offline_mode", False):
        result = _platform_gps()
        if result:
            return result

    # Offline fallback — last known position
    lat = config.get("last_gps_lat") or config.get("latitude")
    lon = config.get("last_gps_lon") or config.get("longitude")
    if lat is not None and lon is not None:
        return _result(lat, lon,
                       source=config.get("last_gps_source", "config"),
                       stale=True)

    return None


def update_position(config: dict, result: dict = None) -> dict:
    """
    Refresh config with a GPS result.  Detects motion and updates is_driving.

    If result is None, calls get_position() internally.
    Returns updated config (caller should save_config if persistance needed).
    """
    if result is None:
        result = get_position(config)
    if result is None:
        return config

    old_lat = config.get("last_gps_lat")
    old_lon = config.get("last_gps_lon")

    config["latitude"]       = result["lat"]
    config["longitude"]      = result["lon"]
    config["last_gps_lat"]   = result["lat"]
    config["last_gps_lon"]   = result["lon"]
    config["last_gps_time"]  = result["timestamp"]
    config["last_gps_source"]= result["source"]

    # Motion detection
    if old_lat is not None and old_lon is not None:
        old = _result(old_lat, old_lon, "config")
        config["is_driving"] = is_moving(old, result)
    else:
        config["is_driving"] = False

    return config


# ── Reverse geocode (Nominatim) ───────────────────────────────────────────────

def _geocache_path(lat: float, lon: float) -> Path:
    """Cache path for reverse geocode results, snapped to ~1 km grid."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    rlat = round(round(lat / _GEOCACHE_GRID) * _GEOCACHE_GRID, 4)
    rlon = round(round(lon / _GEOCACHE_GRID) * _GEOCACHE_GRID, 4)
    return CACHE_DIR / f"cs_revgeo_{rlat}_{rlon}.json"


def _geocache_load(path: Path) -> dict | None:
    """Return cached reverse geocode result if fresh enough."""
    if not path.exists():
        return None
    age = (datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)).total_seconds()
    if age < _GEOCACHE_TTL:
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return None


def reverse_geocode(lat: float, lon: float) -> dict:
    """
    Reverse geocode lat/lon to highway + direction city using Nominatim (OSM).
    No API key required.  Results cached for 5 minutes.

    Returns:
        {
          "highway":    str | None,   # "I-76", "US-30", "PA-283", etc.
          "road":       str | None,   # full road name
          "city":       str | None,
          "state":      str | None,
          "country":    str | None,
          "raw":        dict,         # full Nominatim address block
        }
    """
    path   = _geocache_path(lat, lon)
    cached = _geocache_load(path)
    if cached:
        return cached

    _empty = {"highway": None, "road": None, "city": None,
              "state": None, "country": None, "raw": {}}

    if True:  # wrapped for easy offline bypass
        try:
            r = requests.get(
                _NOMINATIM_URL,
                params={"lat": lat, "lon": lon, "format": "json", "zoom": 18},
                headers=_NOMINATIM_HDR,
                timeout=5,
            )
            r.raise_for_status()
            data    = r.json()
            address = data.get("address", {})

            # Extract highway reference (e.g. "I-76;PA Turnpike" → "I-76")
            ref = address.get("ref", "") or ""
            highway = ref.split(";")[0].strip() if ref else None

            # City fallback chain: city → town → village → county
            city = (address.get("city")
                    or address.get("town")
                    or address.get("village")
                    or address.get("county", ""))

            result = {
                "highway": highway or None,
                "road":    address.get("road"),
                "city":    city or None,
                "state":   address.get("state"),
                "country": address.get("country_code", "").upper() or None,
                "raw":     address,
            }
            path.write_text(json.dumps(result))
            return result

        except Exception as e:
            print(f"⚠  Reverse geocode error: {e}", file=sys.stderr)

    return _empty


def estimate_mile_marker(lat: float, lon: float, highway: str) -> int | None:
    """
    Estimate mile marker along a US Interstate from coordinates.

    This is a rough approximation based on known highway endpoints.
    Accuracy: ± 5-10 miles on straight corridors, worse on curves.

    Returns integer MM estimate or None if highway not in lookup table.

    TODO: Replace with FHWA Linear Referencing System data for production.
    """
    # Known approximate endpoints for common US interstates
    # Format: { "I-XX": ((start_lat, start_lon, mm_start), (end_lat, end_lon, mm_end)) }
    _KNOWN = {
        "I-76":  ((39.96, -75.17, 0),   (41.01, -80.06, 358)),   # PA Turnpike (Philadelphia → Ohio)
        "I-80":  ((40.73, -74.03, 0),   (41.76, -124.18, 2902)), # NJ → CA
        "I-90":  ((42.36, -71.06, 0),   (47.60, -122.33, 3102)), # Boston → Seattle
        "I-40":  ((35.04, -75.56, 0),   (35.19, -117.03, 2555)), # Wilmington → Barstow
        "I-10":  ((30.42, -81.65, 0),   (34.04, -118.25, 2460)), # Jacksonville → LA
        "I-70":  ((39.75, -104.99, 0),  (38.63, -90.19, 2153)),  # Denver → St. Louis
        "I-35":  ((29.42, -98.49, 0),   (46.87, -96.79, 1568)),  # San Antonio → Duluth
        "I-95":  ((25.77, -80.19, 0),   (47.46, -70.01, 1920)),  # Miami → Houlton
        "I-81":  ((36.52, -82.55, 0),   (44.87, -75.83, 855)),   # Tennessee → NY
        "I-65":  ((30.67, -88.07, 0),   (41.88, -87.63, 887)),   # Mobile → Chicago
    }
    entry = _KNOWN.get(highway)
    if not entry:
        return None

    (s_lat, s_lon, mm_s), (e_lat, e_lon, mm_e) = entry
    total_dist = haversine(s_lat, s_lon, e_lat, e_lon)
    if total_dist == 0:
        return mm_s

    driver_from_start = haversine(s_lat, s_lon, lat, lon)
    fraction = min(driver_from_start / total_dist, 1.0)
    return round(mm_s + fraction * (mm_e - mm_s))


# ── Language-aware location description ───────────────────────────────────────

def describe_location(lat: float, lon: float, config: dict,
                      prev_lat: float = None, prev_lon: float = None) -> str:
    """
    Build a human-readable location string in the driver's language.

    Uses travel direction (if prev position available) for bearing.
    Falls back gracefully: highway+city → city only → coordinates.

    Examples (en):
        "I-76 Eastbound near MM142"
        "I-76 Eastbound near Harrisburg, PA"
        "Near Pittsburgh, Pennsylvania"
        "(40.4406, -79.9959)"

    Examples (es):
        "I-76 dirección este cerca del MM142"
        "I-76 dirección este cerca de Pittsburgh, PA"
    """
    # Initialise i18n from config
    lang = config.get("language", "en")
    set_language(lang)

    geo = reverse_geocode(lat, lon)

    # Cardinal direction from travel bearing
    cardinal = None
    if prev_lat is not None and prev_lon is not None:
        try:
            b = bearing(prev_lat, prev_lon, lat, lon)
            if haversine(prev_lat, prev_lon, lat, lon) > 0.01:
                cardinal = bearing_to_cardinal(b)
        except Exception:
            pass

    highway   = geo.get("highway")
    city      = geo.get("city")
    state     = geo.get("state", "")
    # Abbreviate state if long (e.g. "Pennsylvania" → keep as-is; API returns full name)

    if highway and cardinal:
        dir_str = t(f"direction.{cardinal}")
        mm = estimate_mile_marker(lat, lon, highway)
        if mm is not None:
            return t("location.highway_near_mm",
                     highway=highway, direction=dir_str, mm=mm)
        if city:
            return t("location.highway_near_city",
                     highway=highway, direction=dir_str, city=city, state=state or "")
        return f"{highway} {dir_str}"

    if highway and city:
        return t("location.near_city", city=city, state=state or "")

    if city:
        return t("location.near_city", city=city, state=state or "")

    return t("location.coordinates",
             lat=f"{lat:.4f}", lon=f"{lon:.4f}")


# ── Geo-confirmation for hazard reports ───────────────────────────────────────

def confirm_hazard_location(hazard_lat: float, hazard_lon: float,
                            config: dict) -> dict:
    """
    Verify that the driver is close enough to a hazard location to confirm it.
    Rejects reports from drivers more than HAZARD_CONFIRM_MI (2 miles) away.

    Returns:
        { "confirmed": bool, "distance_mi": float, "message": str }
    """
    lang = config.get("language", "en")
    set_language(lang)

    pos = get_position(config)
    if pos is None:
        return {
            "confirmed":   False,
            "distance_mi": None,
            "message":     t("hazard.no_position"),
        }

    dist = haversine(pos["lat"], pos["lon"], hazard_lat, hazard_lon)
    if dist <= HAZARD_CONFIRM_MI:
        return {
            "confirmed":   True,
            "distance_mi": dist,
            "message":     t("hazard.confirmed"),
        }
    return {
        "confirmed":   False,
        "distance_mi": dist,
        "message":     t("hazard.too_far", dist=dist),
    }


# ── Background poll loop ──────────────────────────────────────────────────────

class PollLoop:
    """
    Background GPS polling thread with adaptive interval.

    Usage:
        def on_pos(result, config):
            print(f"Now at {result['lat']}, {result['lon']}")

        loop = PollLoop(config, on_position=on_pos)
        loop.start()
        ...
        loop.stop()

    Callbacks:
        on_position(result: dict, config: dict)
            Called every poll cycle when a position is obtained.

        on_motion_change(is_driving: bool, config: dict)  [optional]
            Called when driving ↔ parked state changes.
            Use this to update HOS guardian and adjust UI refresh rate.
    """

    def __init__(self, config: dict,
                 on_position,
                 on_motion_change=None):
        self._config           = config
        self._on_position      = on_position
        self._on_motion_change = on_motion_change
        self._stop             = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background polling thread."""
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop,
                                        daemon=True,
                                        name="gps-poll")
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the polling thread to stop and wait for it to exit."""
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                was_driving = self._config.get("is_driving", False)
                result      = get_position(self._config)

                if result:
                    self._config  = update_position(self._config, result)
                    now_driving   = self._config.get("is_driving", False)

                    self._on_position(result, self._config)

                    if (self._on_motion_change is not None
                            and was_driving != now_driving):
                        self._on_motion_change(now_driving, self._config)

            except Exception as exc:
                print(f"⚠  GPS poll error: {exc}", file=sys.stderr)

            interval = get_poll_interval(self._config)
            self._stop.wait(interval)
