#!/usr/bin/env python3
from __future__ import annotations
# core/dot511.py — Clean Shot: DOT/511 + Road511 Integration

import json
import re
import shutil
import sys
import time
from pathlib import Path

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

from core.cache import (
    cache_load, cache_save, cache_stale,
    dot511_cache_path, DOT511_CACHE_TIME,
)
from core.subscription import has_feature
from core.config import get_config

_HEADERS = {"User-Agent": "clean-shot/3.0 (bluecollarnation@proton.me)"}

# Road511 Headers (uses X-API-Key)
_ROAD511_HEADERS = lambda key: {"X-API-Key": key, **_HEADERS}

# ── State Feeds (keep your existing dict or simplified) ─────────────────────
STATE_FEEDS = { ... }  # your existing one is fine

# Keep all your _STATE_BOUNDS, regexes, _NWS_EVENT_TYPE, helpers, parsers exactly as before
# (I'm not repeating 600+ lines here — keep everything from your last version)

# ── New: Road511 Fetcher ─────────────────────────────────────────────────────

def _fetch_road511(lat: float, lon: float, config: dict) -> list:
    """Primary high-quality source when API key is available."""
    key = config.get("road511_api_key")
    if not key or not _REQUESTS_AVAILABLE:
        return []

    path = dot511_cache_path(lat, lon)  # reuse same cache for now
    cached, _ = cache_load(path, DOT511_CACHE_TIME)
    if cached:
        try:
            data = json.loads(cached)
            if isinstance(data, dict) and "road511" in data:
                return data["road511"]
        except Exception:
            pass

    try:
        radius = config.get("road511_radius_km", 80)
        url = (f"https://api.road511.com/api/v1/events"
               f"?lat={lat:.4f}&lon={lon:.4f}&radius={radius}"
               f"&status=active&severity=major,moderate,minor")

        r = requests.get(url, headers=_ROAD511_HEADERS(key), timeout=10)
        r.raise_for_status()
        events = r.json().get("events", []) if isinstance(r.json(), dict) else []

        # Normalize Road511 events to your incident format
        incidents = []
        for e in events[:15]:  # limit for performance
            props = e.get("properties", {}) if isinstance(e, dict) else e
            inc = {
                "type": props.get("type", "incident").lower().replace(" ", "_"),
                "severity": props.get("severity", "medium").lower(),
                "highway": props.get("road", None),
                "direction": props.get("direction", "unknown"),
                "description": props.get("description", "")[:100],
                "source": "road511",
                "expires": None,  # Road511 usually has end time
                "truck_only": "truck" in str(props).lower(),
            }
            incidents.append(inc)

        # Cache combined result
        cache_save(path, json.dumps({"road511": incidents}))
        return incidents

    except Exception as e:
        print(f"⚠ Road511 fetch error: {e}", file=sys.stderr)
        return []


# ── Updated Main Fetch ───────────────────────────────────────────────────────

def fetch_dot511(lat: float, lon: float, config: dict = None) -> list:
    if config is None:
        config = get_config()

    incidents = []

    # Priority 1: Road511 (best quality)
    if config.get("road511_enabled"):
        incidents.extend(_fetch_road511(lat, lon, config))

    # Priority 2: NWS (free weather advisories)
    if not incidents or len(incidents) < 5:
        features = _fetch_nws_features(lat, lon)
        incidents.extend(parse_nws_features(features))

    # Priority 3: State feeds (fallback)
    state = _lat_lon_to_state(lat, lon)
    if state:
        incidents.extend(_fetch_state_feed(state, config))

    return filter_truck_relevant(incidents, config)


# Keep all your other functions: get_active_incidents, display_dot511, etc.
# (They will now benefit from richer Road511 data automatically)
