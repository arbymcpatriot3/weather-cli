#!/usr/bin/env python3
from __future__ import annotations
# core/dot511.py — Clean Shot: DOT/511 + Road511 integration
# Primary source: NWS api.weather.gov/alerts (free, all 50 states, no key)
# High-quality source: Road511 API (when api key is configured)
# Fallback: state 511 feeds (added to STATE_FEEDS as public URLs become available)

import json
import re
import sys
from datetime import datetime
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

_HEADERS = {"User-Agent": "clean-shot/3.0 (cleanshothq@pm.me)"}

# ── State codes (50 states + DC) ─────────────────────────────────────────────

STATE_CODES = (
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL",
    "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
)

# State 511 feed URLs — all None until a confirmed-free public feed is available.
# Add URL when a state publishes open data: STATE_FEEDS["CO"] = "https://..."
STATE_FEEDS = {s: None for s in STATE_CODES}

# ── State bounding boxes (lat_min, lat_max, lon_min, lon_max) ─────────────────
_STATE_BOUNDS = {
    "AL": (30.2, 35.0, -88.5, -84.9),
    "AK": (54.5, 71.5, -168.0, -130.0),
    "AZ": (31.3, 37.0, -114.8, -109.0),
    "AR": (33.0, 36.5, -94.6, -89.6),
    "CA": (32.5, 42.0, -124.5, -114.1),
    "CO": (37.0, 41.0, -109.1, -102.0),
    "CT": (40.9, 42.1, -73.7, -71.8),
    "DE": (38.4, 39.9, -75.8, -75.0),
    "DC": (38.8, 39.0, -77.1, -77.0),
    "FL": (24.4, 31.1, -87.7, -79.9),
    "GA": (30.4, 35.0, -85.6, -80.8),
    "HI": (18.9, 22.3, -160.3, -154.8),
    "ID": (42.0, 49.0, -117.2, -111.0),
    "IL": (36.9, 42.5, -91.5, -87.0),
    "IN": (37.8, 41.8, -88.1, -84.8),
    "IA": (40.4, 43.5, -96.6, -90.1),
    "KS": (37.0, 40.0, -102.1, -94.6),
    "KY": (36.5, 39.2, -89.6, -81.9),
    "LA": (28.9, 33.0, -94.0, -88.8),
    "ME": (43.0, 47.5, -71.1, -66.9),
    "MD": (37.9, 39.7, -79.5, -75.0),
    "MA": (41.2, 42.9, -73.5, -69.9),
    "MI": (41.7, 48.3, -90.4, -82.4),
    "MN": (43.5, 49.4, -97.2, -89.5),
    "MS": (30.2, 35.0, -91.7, -88.1),
    "MO": (36.0, 40.6, -95.8, -89.1),
    "MT": (44.4, 49.0, -116.0, -104.0),
    "NE": (40.0, 43.0, -104.1, -95.3),
    "NV": (35.0, 42.0, -120.0, -114.0),
    "NH": (42.7, 45.3, -72.6, -70.6),
    "NJ": (38.9, 41.4, -75.6, -73.9),
    "NM": (31.3, 37.0, -109.1, -103.0),
    "NY": (40.5, 45.0, -79.8, -71.9),
    "NC": (33.8, 36.6, -84.3, -75.5),
    "ND": (45.9, 49.0, -104.1, -96.6),
    "OH": (38.4, 42.3, -84.8, -80.5),
    "OK": (33.6, 37.0, -103.0, -94.4),
    "OR": (42.0, 46.3, -124.7, -116.5),
    "PA": (39.7, 42.3, -80.5, -74.7),
    "RI": (41.1, 42.0, -71.9, -71.1),
    "SC": (32.0, 35.2, -83.4, -78.5),
    "SD": (42.5, 45.9, -104.1, -96.4),
    "TN": (35.0, 36.7, -90.3, -81.7),
    "TX": (25.8, 36.5, -106.7, -93.5),
    "UT": (37.0, 42.0, -114.1, -109.0),
    "VT": (42.7, 45.0, -73.4, -71.5),
    "VA": (36.5, 39.5, -83.7, -75.2),
    "WA": (45.5, 49.0, -124.8, -116.9),
    "WV": (37.2, 40.6, -82.6, -77.7),
    "WI": (42.5, 47.1, -92.9, -86.2),
    "WY": (41.0, 45.0, -111.1, -104.1),
}

# ── NWS event → incident type mapping ────────────────────────────────────────

_NWS_EVENT_TYPE = {
    "winter storm":     "weather_advisory",
    "blizzard":         "weather_advisory",
    "ice storm":        "weather_advisory",
    "freeze":           "weather_advisory",
    "frost":            "weather_advisory",
    "dense fog":        "weather_advisory",
    "fog":              "weather_advisory",
    "high wind":        "weather_advisory",
    "wind advisory":    "weather_advisory",
    "dust storm":       "weather_advisory",
    "blowing dust":     "weather_advisory",
    "flash flood":      "weather_advisory",
    "flood":            "weather_advisory",
    "avalanche":        "weather_advisory",
    "road closure":     "closure",
    "closure":          "closure",
}

# NWS events to skip — not relevant to truckers
_SKIP_EVENTS = frozenset({
    "special marine warning", "marine weather statement",
    "rip current statement", "coastal flood advisory",
    "coastal flood warning", "surf advisory", "surf zone forecast",
    "tornado warning", "tornado watch", "tropical storm warning",
    "tropical storm watch", "tsunami warning", "tsunami watch",
    "red flag warning", "fire weather watch",
    "beach hazards statement", "lake wind advisory",
    "lakeshore flood advisory", "lakeshore flood warning",
})


# ── Pure helper functions (all offline-testable) ───────────────────────────────

def _nws_event_to_type(event_name: str) -> str:
    """Map NWS event name to CleanShot incident type."""
    lower = event_name.lower()
    for key, itype in _NWS_EVENT_TYPE.items():
        if key in lower:
            return itype
    return "weather_advisory"


def _nws_severity(nws_sev: str, urgency: str) -> str:
    """Map NWS severity + urgency to CleanShot severity string."""
    sev = (nws_sev or "").lower()
    urg = (urgency or "").lower()
    if sev == "extreme":
        return "critical"
    if sev == "severe":
        return "high"
    if sev == "moderate":
        return "medium" if urg == "immediate" else "low"
    return "low"


def _has_chain_requirement(text: str) -> bool:
    """Return True if text contains a chain/traction control requirement."""
    lower = (text or "").lower()
    patterns = [
        r"\bchain control\b", r"\bchain law\b",
        r"\bchains? required\b", r"\bchains? enforced\b",
        r"\bchains?\b",
        r"\btraction law\b", r"\btraction control\b",
        r"\bno bare tires?\b", r"\btire chains?\b",
    ]
    return any(re.search(p, lower) for p in patterns)


def _extract_highway(text: str) -> str | None:
    """Extract highway designation from text, normalized."""
    if not text:
        return None
    m = re.search(r'\bI-(\d+[NSEW]?)\b', text, re.IGNORECASE)
    if m:
        return f"I-{m.group(1).upper()}"
    m = re.search(r'\bUS[- ](\d+)\b', text, re.IGNORECASE)
    if m:
        return f"US-{m.group(1)}"
    m = re.search(r'\bHighway[- ](\d+)\b', text, re.IGNORECASE)
    if m:
        return f"HIGHWAY-{m.group(1)}"
    m = re.search(r'\bHwy[- ](\d+)\b', text, re.IGNORECASE)
    if m:
        return f"HWY-{m.group(1)}"
    return None


def _extract_direction(text: str) -> str:
    """Extract travel direction from text."""
    lower = (text or "").lower()
    if "both direction" in lower or "both ways" in lower:
        return "both"
    for d in ("northbound", "southbound", "eastbound", "westbound"):
        if d in lower:
            return d
    return "unknown"


def _iso_to_unix(iso_str: str | None) -> int | None:
    """Convert ISO 8601 timestamp string to Unix int, or None on failure."""
    if not iso_str:
        return None
    try:
        s = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return int(dt.timestamp())
    except Exception:
        return None


def _truncate_desc(text: str, max_len: int) -> str:
    """Truncate text at a word boundary to max_len, appending '…' if cut."""
    if not text or len(text) <= max_len:
        return text
    truncated = text[:max_len]
    last_space = truncated.rfind(" ")
    if last_space > max_len // 2:
        truncated = truncated[:last_space]
    return truncated + "…"


def _lat_lon_to_state(lat: float, lon: float) -> str | None:
    """Return US state code from lat/lon via bounding box lookup, or None."""
    for state, (lat_min, lat_max, lon_min, lon_max) in _STATE_BOUNDS.items():
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return state
    return None


# ── NWS feature parsing ───────────────────────────────────────────────────────

def _parse_nws_feature(feature: dict) -> dict | None:
    """Parse a single NWS GeoJSON alert feature into a CleanShot incident dict.
    Returns None for non-truck-relevant events."""
    props = feature.get("properties", {})
    if not props:
        return None

    event = props.get("event", "")
    if not event:
        return None

    if event.lower() in _SKIP_EVENTS:
        return None

    headline    = props.get("headline", "")
    description = props.get("description", "")
    text        = f"{headline} {description}"

    itype    = _nws_event_to_type(event)
    severity = _nws_severity(props.get("severity", ""), props.get("urgency", ""))

    if _has_chain_requirement(headline) or _has_chain_requirement(description):
        itype = "chains_required"

    desc = _truncate_desc(headline or description or event, 100)

    return {
        "type":        itype,
        "severity":    severity,
        "highway":     _extract_highway(text),
        "direction":   _extract_direction(text),
        "description": desc,
        "source":      "nws",
        "expires":     _iso_to_unix(props.get("expires")),
        "truck_only":  False,
    }


def parse_nws_features(features: list) -> list:
    """Parse a list of NWS GeoJSON features into CleanShot incident dicts."""
    incidents = []
    for f in features:
        inc = _parse_nws_feature(f)
        if inc is not None:
            incidents.append(inc)
    return incidents


# ── Network fetchers ──────────────────────────────────────────────────────────

def _fetch_nws_features(lat: float, lon: float) -> list:
    """Fetch NWS active alerts for lat/lon. Returns feature list or []."""
    if not _REQUESTS_AVAILABLE:
        return []
    try:
        url = f"https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}"
        r = requests.get(url, headers=_HEADERS, timeout=10)
        r.raise_for_status()
        return r.json().get("features", [])
    except Exception:
        return []


def _fetch_state_feed(state: str, config: dict) -> list:
    """Fetch from a state-specific 511 feed if a URL is configured."""
    url = STATE_FEEDS.get(state)
    if not url or not _REQUESTS_AVAILABLE:
        return []
    try:
        r = requests.get(url, headers=_HEADERS, timeout=10)
        r.raise_for_status()
        return []  # TODO: parse per-state feed format when feeds are added
    except Exception:
        return []


# ── Filtering ─────────────────────────────────────────────────────────────────

def filter_truck_relevant(incidents: list, config: dict = None) -> list:
    """Filter and score incidents for truck relevance. Returns sorted list."""
    if not incidents:
        return []
    if config is None:
        config = {}

    relevant = []
    for inc in incidents:
        itype = inc.get("type", "")
        sev   = inc.get("severity", "low")

        # Always include these critical incident types regardless of severity
        if itype in ("chains_required", "closure", "bridge_restriction",
                     "weigh_station", "weight_restriction"):
            inc["risk_score"] = 90 if sev in ("critical", "high") else 70
            relevant.append(inc)
            continue

        # High/critical severity weather always matters
        if sev in ("critical", "high"):
            inc["risk_score"] = 80
            relevant.append(inc)
            continue

        # Incidents and construction always pass through
        if itype in ("incident", "construction"):
            inc["risk_score"] = 50
            relevant.append(inc)
            continue

        # Medium severity weather advisory
        if itype == "weather_advisory" and sev == "medium":
            inc["risk_score"] = 40
            relevant.append(inc)
            continue

        # Truck-specific items always pass
        if inc.get("truck_only") or inc.get("truck_relevant"):
            inc["risk_score"] = 75
            relevant.append(inc)

    relevant.sort(key=lambda x: x.get("risk_score", 0), reverse=True)
    return relevant


# ── Main fetch ────────────────────────────────────────────────────────────────

def fetch_dot511(lat: float, lon: float, config: dict = None) -> list:
    """Fetch road incidents. Priority: Road511 → NWS → state feeds."""
    if config is None:
        config = get_config()

    incidents = []

    # Priority 1: Road511 (best quality, Starter plan)
    if config.get("road511_enabled") and config.get("road511_api_key"):
        try:
            from core.road511 import fetch_events as _r511_events
            incidents.extend(_r511_events(lat, lon, config))
        except Exception:
            pass

    # Priority 2: NWS weather advisories (free fallback)
    if not incidents or len(incidents) < 3:
        features = _fetch_nws_features(lat, lon)
        incidents.extend(parse_nws_features(features))

    # Priority 3: State feeds (legacy fallback)
    if not incidents:
        state = _lat_lon_to_state(lat, lon)
        if state:
            incidents.extend(_fetch_state_feed(state, config))

    return filter_truck_relevant(incidents, config)


def get_active_incidents(lat: float, lon: float, config: dict = None) -> list:
    """Gate-checked, cached fetch of active incidents sorted critical-first."""
    if config is None:
        config = get_config()
    if not has_feature(config, "dot511"):
        return []

    cache_path = dot511_cache_path(lat, lon)
    cached, _  = cache_load(cache_path, DOT511_CACHE_TIME)
    if cached:
        try:
            data = json.loads(cached)
            if isinstance(data, list):
                return data
        except Exception:
            pass

    incidents = fetch_dot511(lat, lon, config)

    try:
        cache_save(cache_path, json.dumps(incidents))
    except Exception:
        pass

    return incidents


# ── TTS ───────────────────────────────────────────────────────────────────────

def speak_dot511_alerts(incidents: list, config: dict = None) -> int:
    """Speak truck-relevant incidents via TTS. Returns count spoken."""
    if config is None:
        config = {}
    if not config.get("tts_enabled"):
        return 0

    try:
        from core.tts import speak_alert
    except ImportError:
        return 0

    _TYPE_TO_TTS = {
        "chains_required":    "chain_control",
        "closure":            "road_closure",
        "weather_advisory":   "weather_advisory",
        "construction":       "incident",
        "bridge_restriction": "bridge_clearance",
        "weight_restriction": "weight_restrict",
        "incident":           "incident",
    }
    _SEV_TO_TTS = {
        "critical": "CRITICAL",
        "high":     "CRITICAL",
        "medium":   "WARNING",
        "low":      "INFO",
    }

    spoken = 0
    for inc in incidents[:5]:
        alert_type = _TYPE_TO_TTS.get(inc.get("type", ""), "incident")
        tts_sev    = _SEV_TO_TTS.get(inc.get("severity", "low"), "INFO")
        try:
            speak_alert(alert_type, tts_sev, config)
            spoken += 1
        except Exception:
            pass

    return spoken


# ── Display ───────────────────────────────────────────────────────────────────

def display_dot511(incidents: list, config: dict = None) -> None:
    """Display DOT/511 incidents as ASCII, max 8 shown."""
    if config is None:
        config = {}

    import shutil
    try:
        from colorama import Fore, Style, init
        init(autoreset=True)
        _color = True
    except ImportError:
        _color = False

    try:
        override = config.get("display_width_override")
        w = (override if isinstance(override, int) and 20 <= override <= 300
             else shutil.get_terminal_size(fallback=(80, 24)).columns)
    except Exception:
        w = 80
    w = max(36, w)

    if not incidents:
        msg = "✓  No active road incidents in your area"
        print(f"\033[32m{msg}\033[0m" if _color else msg)
        return

    count = len(incidents)
    print(f"\n  Road Conditions ({count} incident{'s' if count != 1 else ''})")
    print("  " + "─" * min(w - 4, 60))

    _SEV_CODES = {
        "critical": "\033[31m",
        "high":     "\033[31m",
        "medium":   "\033[33m",
        "low":      "\033[37m",
    }
    _RESET = "\033[0m"

    _TAGS = {
        "chains_required":    "[C]",
        "closure":            "[X]",
        "construction":       "[~]",
        "bridge_restriction": "[B]",
        "weight_restriction": "[W]",
        "weather_advisory":   "[!]",
        "incident":           "[!]",
    }

    for inc in incidents[:8]:
        sev  = inc.get("severity", "low")
        tag  = _TAGS.get(inc.get("type", ""), "[?]")
        road = inc.get("highway") or ""
        desc = inc.get("description", "")
        col  = _SEV_CODES.get(sev, "") if _color else ""
        rst  = _RESET if _color else ""

        road_str = f" {road}" if road else ""
        line     = f"  {col}{tag}{rst}{road_str} {desc}"
        if len(line) > w + len(col) + len(rst):
            line = line[:w - 1] + "…"
        print(line)
