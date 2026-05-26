#!/usr/bin/env python3
from __future__ import annotations
# core/road511.py — Clean Shot: Road511 API client (Starter plan)
# All functions fail silently — a network error never crashes the app.
# Cache TTLs: incidents=15min, bridges=24h, route=1h, features=15min, cameras=2min

import json
import sys
from pathlib import Path

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

from core.cache import (
    cache_load, cache_save,
    dot511_cache_path, DOT511_CACHE_TIME,
    bridge_cache_path, BRIDGE_CACHE_TIME,
    route_cache_path, TRUCK_ROUTE_CACHE,
    feature_cache_path, FEATURE_CACHE_TIME,
    CAMERA_CACHE_TIME,
)

_BASE    = "https://api.road511.com/api/v1"
_UA      = {"User-Agent": "clean-shot/3.0 (cleanshothq@pm.me)"}


def _h(key: str) -> dict:
    """Build request headers with API key."""
    return {"X-API-Key": key, **_UA}


def _get(url: str, key: str, timeout: int = 10) -> dict | None:
    """GET request returning parsed JSON or None on any error."""
    if not _REQUESTS_AVAILABLE or not key:
        return None
    try:
        r = _requests.get(url, headers=_h(key), timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠ Road511 error: {e}", file=sys.stderr)
        return None


def _post(url: str, key: str, body: dict, timeout: int = 15) -> dict | None:
    """POST request returning parsed JSON or None on any error."""
    if not _REQUESTS_AVAILABLE or not key:
        return None
    try:
        r = _requests.post(url, headers=_h(key), json=body, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠ Road511 routing error: {e}", file=sys.stderr)
        return None


# ── 3b. fetch_events ──────────────────────────────────────────────────────────

def fetch_events(lat: float, lon: float, config: dict) -> list:
    """Fetch active road events from Road511 within radius. Returns normalized incidents."""
    key = config.get("road511_api_key")
    if not key:
        return []

    cache_path = dot511_cache_path(lat, lon)
    cached, _  = cache_load(cache_path, DOT511_CACHE_TIME)
    if cached:
        try:
            data = json.loads(cached)
            if isinstance(data, dict) and "r511_events" in data:
                return data["r511_events"]
        except Exception:
            pass

    radius = config.get("road511_radius_km", 80)
    url    = (f"{_BASE}/events"
              f"?lat={lat:.4f}&lon={lon:.4f}&radius_km={radius}"
              f"&status=active")
    data   = _get(url, key)
    if data is None:
        return []

    raw_events = data.get("features") or data.get("events") or []
    incidents  = []
    for e in raw_events[:20]:
        props = e.get("properties", e) if isinstance(e, dict) else {}
        raw_type = str(props.get("type", "incident")).lower().replace(" ", "_")
        inc = {
            "source":         "road511",
            "type":           raw_type if raw_type in (
                "incident", "construction", "closure", "weather",
                "chain_control", "weight_restriction"
            ) else "incident",
            "severity":       _map_severity(props.get("severity", "")),
            "road":           str(props.get("road", "")),
            "direction":      str(props.get("direction", "unknown")),
            "description":    str(props.get("description", ""))[:120],
            "truck_relevant": "truck" in str(props).lower(),
            "expires":        props.get("end_time") or props.get("expires"),
            "risk_score":     0,
        }
        incidents.append(inc)

    try:
        cache_save(cache_path, json.dumps({"r511_events": incidents}))
    except Exception:
        pass

    return incidents


def _map_severity(raw: str) -> str:
    """Normalize Road511 severity string to CleanShot severity."""
    r = (raw or "").lower()
    if r in ("critical", "major"):
        return "critical"
    if r in ("severe", "high"):
        return "high"
    if r in ("moderate", "medium"):
        return "medium"
    return "low"


# ── 3c. fetch_bridges ─────────────────────────────────────────────────────────

def fetch_bridges(lat: float, lon: float, config: dict) -> list:
    """Fetch bridge clearances within radius. Flags low-clearance bridges."""
    key = config.get("road511_api_key")
    if not key:
        return []

    cache_path = bridge_cache_path(lat, lon)
    cached, _  = cache_load(cache_path, BRIDGE_CACHE_TIME)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    radius = config.get("road511_radius_km", 80)
    url    = (f"{_BASE}/features"
              f"?type=bridge_clearances&lat={lat:.4f}&lon={lon:.4f}&radius_km={radius}")
    data   = _get(url, key)
    if data is None:
        return []

    height    = config.get("vehicle_height_ft", 13.5) or 13.5
    features  = data.get("features") or []
    bridges   = []
    for f in features:
        props = f.get("properties", f) if isinstance(f, dict) else {}
        geom  = f.get("geometry", {}) if isinstance(f, dict) else {}
        coords = geom.get("coordinates", [None, None]) if geom else [None, None]
        try:
            blat = float(coords[1]) if len(coords) > 1 else lat
            blon = float(coords[0]) if len(coords) > 0 else lon
        except (TypeError, ValueError):
            blat, blon = lat, lon

        try:
            clearance = float(props.get("clearance_ft", 99))
        except (TypeError, ValueError):
            clearance = 99.0

        try:
            weight_limit = float(props.get("weight_limit_tons", 0)) or None
        except (TypeError, ValueError):
            weight_limit = None

        bridges.append({
            "source":            "road511_nbi",
            "type":              "bridge_clearance",
            "road":              str(props.get("road", "")),
            "name":              props.get("name") or None,
            "clearance_ft":      clearance,
            "weight_limit_tons": weight_limit,
            "lat":               blat,
            "lon":               blon,
            "flagged":           clearance < height + 0.5,
        })

    try:
        cache_save(cache_path, json.dumps(bridges))
    except Exception:
        pass

    return bridges


# ── 3d. fetch_truck_routing ───────────────────────────────────────────────────

def fetch_truck_routing(origin: dict, destination: dict, config: dict) -> dict:
    """POST truck-safe routing request. origin/destination: {lat, lon}."""
    key = config.get("road511_api_key")
    if not key:
        return {"safe": True, "warnings": [], "bridge_alerts": [],
                "weight_alerts": [], "distance_miles": 0.0,
                "duration_min": 0.0, "staa_route": False}

    cache_path = route_cache_path(
        origin["lat"], origin["lon"],
        destination["lat"], destination["lon"]
    )
    cached, _ = cache_load(cache_path, TRUCK_ROUTE_CACHE)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    body = {
        "origin":      {"lat": origin["lat"], "lon": origin["lon"]},
        "destination": {"lat": destination["lat"], "lon": destination["lon"]},
        "vehicle": {
            "height_ft":  config.get("vehicle_height_ft", 13.5),
            "weight_lbs": config.get("vehicle_weight_lbs", 80000),
            "length_ft":  config.get("vehicle_length_ft", 75),
            "type":       config.get("vehicle_type", "semi"),
        },
    }

    data = _post(f"{_BASE}/routing/truck", key, body)
    if data is None:
        return {"safe": True, "warnings": [], "bridge_alerts": [],
                "weight_alerts": [], "distance_miles": 0.0,
                "duration_min": 0.0, "staa_route": False}

    result = {
        "safe":           bool(data.get("safe", True)),
        "warnings":       list(data.get("warnings", [])),
        "bridge_alerts":  list(data.get("bridge_alerts", [])),
        "weight_alerts":  list(data.get("weight_alerts", [])),
        "distance_miles": float(data.get("distance_miles", 0)),
        "duration_min":   float(data.get("duration_min", 0)),
        "staa_route":     bool(data.get("staa_route", False)),
    }

    try:
        cache_save(cache_path, json.dumps(result))
    except Exception:
        pass

    return result


# ── 3e. fetch_weigh_stations ──────────────────────────────────────────────────

def fetch_weigh_stations(lat: float, lon: float, config: dict) -> list:
    """Fetch weigh station status within 50 miles, sorted by distance."""
    key = config.get("road511_api_key")
    if not key:
        return []

    cache_path = feature_cache_path(lat, lon, "weigh")
    cached, _  = cache_load(cache_path, FEATURE_CACHE_TIME)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    url  = f"{_BASE}/features?type=weigh_stations&lat={lat:.4f}&lon={lon:.4f}&radius_km=80"
    data = _get(url, key)
    if data is None:
        return []

    try:
        from core.gps import haversine as _hav
    except ImportError:
        _hav = None

    features = data.get("features") or []
    stations = []
    for f in features:
        props = f.get("properties", f) if isinstance(f, dict) else {}
        geom  = f.get("geometry", {}) if isinstance(f, dict) else {}
        coords = geom.get("coordinates", [None, None]) if geom else [None, None]
        try:
            slat = float(coords[1]) if len(coords) > 1 else lat
            slon = float(coords[0]) if len(coords) > 0 else lon
        except (TypeError, ValueError):
            slat, slon = lat, lon

        dist_mi = 0.0
        if _hav:
            try:
                dist_mi = round(_hav(lat, lon, slat, slon), 1)
            except Exception:
                pass

        if dist_mi > 50:
            continue

        raw_status = str(props.get("status", "unknown")).lower()
        if raw_status in ("open", "1", "true"):
            status = "open"
        elif raw_status in ("closed", "0", "false"):
            status = "closed"
        else:
            status = "unknown"

        stations.append({
            "source":         "road511",
            "type":           "weigh_station",
            "name":           str(props.get("name", "Weigh Station")),
            "road":           str(props.get("road", "")),
            "direction":      str(props.get("direction", "unknown")),
            "status":         status,
            "distance_miles": dist_mi,
            "lat":            slat,
            "lon":            slon,
        })

    stations.sort(key=lambda s: s["distance_miles"])

    try:
        cache_save(cache_path, json.dumps(stations))
    except Exception:
        pass

    return stations


# ── 3f. fetch_truck_parking ───────────────────────────────────────────────────

def fetch_truck_parking(lat: float, lon: float, config: dict) -> list:
    """Fetch Road511 truck parking within 50 miles, sorted by distance."""
    key = config.get("road511_api_key")
    if not key:
        return []

    cache_path = feature_cache_path(lat, lon, "r511park")
    cached, _  = cache_load(cache_path, FEATURE_CACHE_TIME)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    url  = f"{_BASE}/features?type=truck_parking&lat={lat:.4f}&lon={lon:.4f}&radius_km=80"
    data = _get(url, key)
    if data is None:
        return []

    try:
        from core.gps import haversine as _hav
    except ImportError:
        _hav = None

    features = data.get("features") or []
    stops    = []
    for f in features:
        props = f.get("properties", f) if isinstance(f, dict) else {}
        geom  = f.get("geometry", {}) if isinstance(f, dict) else {}
        coords = geom.get("coordinates", [None, None]) if geom else [None, None]
        try:
            slat = float(coords[1]) if len(coords) > 1 else lat
            slon = float(coords[0]) if len(coords) > 0 else lon
        except (TypeError, ValueError):
            slat, slon = lat, lon

        dist_mi = 0.0
        if _hav:
            try:
                dist_mi = round(_hav(lat, lon, slat, slon), 1)
            except Exception:
                pass

        if dist_mi > 50:
            continue

        raw_amen = props.get("amenities") or []
        amenities = list(raw_amen) if isinstance(raw_amen, list) else []

        try:
            spaces = int(props.get("spaces", 0)) or None
        except (TypeError, ValueError):
            spaces = None

        stops.append({
            "source":         "road511",
            "name":           str(props.get("name", "Truck Parking")),
            "road":           str(props.get("road", "")),
            "spaces":         spaces,
            "amenities":      amenities,
            "lat":            slat,
            "lon":            slon,
            "distance_miles": dist_mi,
        })

    stops.sort(key=lambda s: s["distance_miles"])

    try:
        cache_save(cache_path, json.dumps(stops))
    except Exception:
        pass

    return stops


# ── 3g. fetch_cameras ─────────────────────────────────────────────────────────

def fetch_cameras(lat: float, lon: float, config: dict) -> list:
    """Fetch live camera links within 30 miles. Only runs if show_cameras=True."""
    if not config.get("show_cameras", False):
        return []

    key = config.get("road511_api_key")
    if not key:
        return []

    cache_path = feature_cache_path(lat, lon, "cameras")
    cached, _  = cache_load(cache_path, CAMERA_CACHE_TIME)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    url  = f"{_BASE}/features?type=cameras&lat={lat:.4f}&lon={lon:.4f}&radius_km=48"
    data = _get(url, key)
    if data is None:
        return []

    try:
        from core.gps import haversine as _hav
    except ImportError:
        _hav = None

    features = data.get("features") or []
    cameras  = []
    for f in features:
        props = f.get("properties", f) if isinstance(f, dict) else {}
        geom  = f.get("geometry", {}) if isinstance(f, dict) else {}
        coords = geom.get("coordinates", [None, None]) if geom else [None, None]
        try:
            clat = float(coords[1]) if len(coords) > 1 else lat
            clon = float(coords[0]) if len(coords) > 0 else lon
        except (TypeError, ValueError):
            clat, clon = lat, lon

        dist_mi = 0.0
        if _hav:
            try:
                dist_mi = round(_hav(lat, lon, clat, clon), 1)
            except Exception:
                pass

        cameras.append({
            "source":         "road511",
            "type":           "camera",
            "road":           str(props.get("road", "")),
            "direction":      str(props.get("direction", "unknown")),
            "image_url":      str(props.get("image_url", "")),
            "distance_miles": dist_mi,
        })

    cameras.sort(key=lambda c: c["distance_miles"])

    try:
        cache_save(cache_path, json.dumps(cameras))
    except Exception:
        pass

    return cameras


# ── 3h. check_route_safety (main orchestrator) ────────────────────────────────

def check_route_safety(lat: float, lon: float, config: dict) -> dict:
    """Full route safety check for the current position.
    Returns a safety report dict — display with display_route_safety()."""
    key = config.get("road511_api_key")
    if not key:
        return {"available": False, "reason": "no_api_key"}

    report = {
        "available":      True,
        "safe":           True,
        "clearance_ok":   True,
        "weight_ok":      True,
        "incidents":      [],
        "bridge_alerts":  [],
        "weigh_stations": [],
        "truck_parking":  [],
        "cameras":        [],
        "warnings":       [],
        "critical":       [],
    }

    # 1. Active incidents
    try:
        incidents = fetch_events(lat, lon, config)
        report["incidents"] = incidents
        critical_inc = [i for i in incidents
                        if i.get("severity") in ("critical", "major", "high")]
        if critical_inc:
            report["safe"] = False
            report["critical"].extend(
                [i["description"] for i in critical_inc[:3]]
            )
    except Exception:
        pass

    # 2. Bridge clearances
    height = config.get("vehicle_height_ft", 13.5) or 13.5
    try:
        bridges = fetch_bridges(lat, lon, config)
        flagged = [b for b in bridges if b.get("flagged")]
        report["bridge_alerts"] = flagged
        if flagged:
            report["safe"]         = False
            report["clearance_ok"] = False
            for b in flagged[:3]:
                report["critical"].append(
                    f"LOW CLEARANCE: {b['road']} bridge — "
                    f"{b['clearance_ft']:.1f} ft "
                    f"(your vehicle: {height:.1f} ft)"
                )
    except Exception:
        pass

    # 3. Weigh stations
    try:
        if config.get("show_weigh_stations", True):
            report["weigh_stations"] = fetch_weigh_stations(lat, lon, config)
    except Exception:
        pass

    # 4. Truck parking (top 5 closest)
    try:
        if config.get("show_truck_parking", True):
            report["truck_parking"] = fetch_truck_parking(lat, lon, config)[:5]
    except Exception:
        pass

    # 5. Cameras (if enabled)
    try:
        if config.get("show_cameras", False):
            report["cameras"] = fetch_cameras(lat, lon, config)
    except Exception:
        pass

    return report
