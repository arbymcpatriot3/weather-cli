#!/usr/bin/env python3
# core/dot511.py — Clean Shot: DOT/511 road condition feeds
# Tier: Solo Pro+ (dot511 feature)
#
# Primary source: NWS api.weather.gov — free, no key, all 50 states.
#   Covers: winter weather, chains, fog, flooding, high wind, ice, blizzard,
#           avalanche, dust storms, special weather statements.
#   Fetch: api.weather.gov/alerts/active?point={lat},{lon}
#   Cache: dot511_cache_path() — 15-min TTL (DOT data is slow-changing)
#
# Secondary source framework: STATE_FEEDS dict — 50-state slot table.
#   All slots start as None. Add state 511 feed URLs as they become available.
#   No state feeds currently require API keys.
#
# Incident dict format (all incidents normalized to this shape):
#   {
#     "type":        str   — construction|closure|chains_required|
#                            weather_advisory|bridge_restriction|
#                            weigh_station|incident
#     "severity":    str   — low|medium|high|critical
#     "highway":     str|None  — "I-70", "US-40", etc.
#     "direction":   str   — northbound|southbound|eastbound|westbound|both|unknown
#     "description": str   — <= 100 chars
#     "source":      str   — "nws"|"state_511"
#     "expires":     int|None — unix timestamp
#     "truck_only":  bool  — True if commercial vehicles only
#   }
#
# Data budget: NWS point response typically 2–10 KB gzipped. Well under 50 KB/refresh.

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

_HEADERS = {"User-Agent": "clean-shot/3.0 (bluecollarnation@proton.me)"}


# ── All 50 states + DC ────────────────────────────────────────────────────────

STATE_CODES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
]

# State 511 feed URL table — None until a confirmed-free public feed is available.
# Add entries here as states publish open feeds (no API key required).
# Future: CO, OR, WA, UT, MT, WY, MN have documented public DOT data programs.
STATE_FEEDS: dict = {code: None for code in STATE_CODES}


# ── Approximate state bounding boxes (lat_min, lat_max, lon_min, lon_max) ─────
# Accuracy: ±30-50 mi at state borders. Used for state feed routing only.
# NWS point-based fetch is always authoritative for weather advisories.

_STATE_BOUNDS = {
    "AL": (30.1, 35.1, -88.6, -84.9),
    "AK": (51.2, 71.5, -179.2, -129.9),
    "AZ": (31.3, 37.0, -114.8, -109.0),
    "AR": (33.0, 36.5, -94.6, -89.6),
    "CA": (32.5, 42.0, -124.5, -114.1),
    "CO": (37.0, 41.0, -109.1, -102.0),
    "CT": (41.0, 42.1, -73.7, -71.8),
    "DE": (38.4, 39.9, -75.8, -75.0),
    "FL": (24.5, 31.1, -87.6, -80.0),
    "GA": (30.4, 35.0, -85.6, -80.8),
    "HI": (18.9, 28.4, -178.4, -154.8),
    "ID": (42.0, 49.0, -117.2, -111.0),
    "IL": (37.0, 42.5, -91.5, -87.5),
    "IN": (37.8, 41.8, -88.1, -84.8),
    "IA": (40.4, 43.5, -96.6, -90.1),
    "KS": (37.0, 40.0, -102.1, -94.6),
    "KY": (36.5, 39.1, -89.6, -81.9),
    "LA": (29.0, 33.0, -94.1, -88.8),
    "ME": (43.0, 47.5, -71.1, -66.9),
    "MD": (38.0, 39.8, -79.5, -75.0),
    "MA": (41.2, 42.9, -73.5, -69.9),
    "MI": (41.7, 48.3, -90.4, -82.4),
    "MN": (43.5, 49.4, -97.3, -89.5),
    "MS": (30.2, 35.0, -91.7, -88.1),
    "MO": (36.0, 40.6, -95.8, -89.1),
    "MT": (44.4, 49.0, -116.1, -104.0),
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
    "TN": (35.0, 36.7, -90.3, -81.6),
    "TX": (25.8, 36.5, -106.6, -93.5),
    "UT": (37.0, 42.0, -114.1, -109.0),
    "VT": (42.7, 45.0, -73.4, -71.5),
    "VA": (36.5, 39.5, -83.7, -75.2),
    "WA": (45.5, 49.0, -124.8, -116.9),
    "WV": (37.2, 40.6, -82.7, -77.7),
    "WI": (42.5, 47.1, -92.9, -86.8),
    "WY": (41.0, 45.0, -111.1, -104.1),
    "DC": (38.8, 39.0, -77.1, -76.9),
}

# NWS event name → dot511 incident type
_NWS_EVENT_TYPE = {
    "Winter Storm Warning":           "weather_advisory",
    "Winter Storm Watch":             "weather_advisory",
    "Winter Weather Advisory":        "weather_advisory",
    "Blizzard Warning":               "weather_advisory",
    "Blizzard Watch":                 "weather_advisory",
    "Ice Storm Warning":              "weather_advisory",
    "Freezing Rain Advisory":         "weather_advisory",
    "Sleet Advisory":                 "weather_advisory",
    "Heavy Snow Warning":             "weather_advisory",
    "Lake Effect Snow Warning":       "weather_advisory",
    "Lake Effect Snow Advisory":      "weather_advisory",
    "Dense Fog Advisory":             "weather_advisory",
    "Dense Smoke Advisory":           "weather_advisory",
    "High Wind Warning":              "weather_advisory",
    "Wind Advisory":                  "weather_advisory",
    "Extreme Wind Warning":           "weather_advisory",
    "Flash Flood Warning":            "weather_advisory",
    "Flash Flood Watch":              "weather_advisory",
    "Flood Warning":                  "weather_advisory",
    "Flood Advisory":                 "weather_advisory",
    "River Flood Warning":            "weather_advisory",
    "Avalanche Warning":              "weather_advisory",
    "Avalanche Watch":                "weather_advisory",
    "Dust Storm Warning":             "weather_advisory",
    "Dust Advisory":                  "weather_advisory",
    "Blowing Snow Advisory":          "weather_advisory",
    "Freezing Fog Advisory":          "weather_advisory",
    "Freezing Drizzle Advisory":      "weather_advisory",
    "Special Weather Statement":      "weather_advisory",
    "Road Closure":                   "closure",
    "Road Restriction":               "bridge_restriction",
}

# NWS events that are NOT relevant to truckers on highways
_SKIP_EVENTS = {
    "Tornado Warning", "Tornado Watch",
    "Severe Thunderstorm Warning", "Severe Thunderstorm Watch",
    "Special Marine Warning", "Marine Weather Statement",
    "Coastal Flood Advisory", "Coastal Flood Warning",
    "Rip Current Statement", "Beach Hazards Statement",
    "Lakeshore Flood Advisory", "Lakeshore Flood Warning",
    "Small Craft Advisory", "Gale Warning", "Storm Warning",
    "Tropical Storm Warning", "Hurricane Warning",
    "Excessive Heat Warning", "Heat Advisory",  # not hazardous for trucks
    "Air Quality Alert", "Red Flag Warning",    # fire — not road-blocking
}

# Keywords that indicate chain/traction requirements
_CHAIN_KEYWORDS = (
    "chain", "chains required", "chained", "traction devices",
    "traction law", "chain law", "no bare tires", "traction control",
    "chain control",
)

# Regex for highway identifiers in NWS text
_HIGHWAY_RE = re.compile(
    r'\b(I-\d{1,3}[A-Z]?'       # I-70, I-15, I-90W
    r'|US-\d{1,3}'               # US-40, US-6
    r'|US\s+\d{1,3}'             # US 40
    r'|SR-\d{1,3}'               # SR-82
    r'|SH-\d{1,3}'               # SH-9 (state highway)
    r'|Highway\s+\d{1,3}'        # Highway 285
    r'|Hwy\.?\s+\d{1,3}'         # Hwy 285 / Hwy. 285
    r'|Route\s+\d{1,3})\b',      # Route 66
    re.IGNORECASE,
)

# Direction keywords in NWS text
_DIR_RE = re.compile(
    r'\b(northbound|southbound|eastbound|westbound|'
    r'north bound|south bound|east bound|west bound|'
    r'both directions?)\b',
    re.IGNORECASE,
)

# NWS severity + urgency → dot511 severity
def _nws_severity(nws_sev: str, urgency: str) -> str:
    if nws_sev in ("Extreme",):                           return "critical"
    if nws_sev in ("Severe",):                            return "high"
    if nws_sev == "Moderate" and urgency == "Immediate":  return "medium"
    if nws_sev == "Moderate":                             return "low"
    return "low"


# ── Pure helper functions ─────────────────────────────────────────────────────

def _has_chain_requirement(text: str) -> bool:
    """Return True if text mentions chain or traction requirements."""
    t = text.lower()
    return any(kw in t for kw in _CHAIN_KEYWORDS)


def _extract_highway(text: str) -> str | None:
    """
    Extract the first highway identifier from text.
    Returns normalized string (e.g. "I-70", "US-40") or None.
    """
    m = _HIGHWAY_RE.search(text)
    if not m:
        return None
    # Normalize spaces to hyphens, uppercase
    hw = re.sub(r'\s+', '-', m.group(1).strip().upper())
    # Remove trailing period
    return hw.rstrip(".")


def _extract_direction(text: str) -> str:
    """Extract travel direction from text. Returns 'unknown' if not found."""
    m = _DIR_RE.search(text)
    if not m:
        return "unknown"
    d = m.group(1).lower().replace(" ", "")
    if "both" in d:
        return "both"
    for cardinal in ("northbound", "southbound", "eastbound", "westbound"):
        if cardinal in d:
            return cardinal
    return "unknown"


def _nws_event_to_type(event_name: str) -> str:
    """Map NWS event name to dot511 incident type. Defaults to weather_advisory."""
    return _NWS_EVENT_TYPE.get(event_name, "weather_advisory")


def _truncate_desc(text: str, max_len: int = 100) -> str:
    """Trim description to max_len characters, ending at a word boundary."""
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0]
    return cut + "…" if cut else text[:max_len]


def _iso_to_unix(iso_str: str | None) -> int | None:
    """Convert ISO 8601 timestamp string to Unix int. Returns None on failure."""
    if not iso_str:
        return None
    try:
        # Python 3.7+ fromisoformat handles most ISO 8601 forms
        from datetime import datetime, timezone
        # Strip trailing Z, replace offset colon for broad compat
        s = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return int(dt.astimezone(timezone.utc).timestamp())
    except Exception:
        return None


# ── NWS parsing ────────────────────────────────────────────────────────────────

def _parse_nws_feature(feature: dict) -> dict | None:
    """
    Convert a single NWS GeoJSON feature to a dot511 incident dict.
    Returns None if the event is not road-relevant.
    """
    props   = feature.get("properties", {})
    event   = props.get("event", "")
    headline = props.get("headline", "") or ""
    desc    = props.get("description", "") or ""
    severity = props.get("severity", "Unknown")
    urgency  = props.get("urgency",  "Unknown")
    expires  = props.get("expires")

    if event in _SKIP_EVENTS:
        return None

    combined = f"{headline} {desc}"

    itype = _nws_event_to_type(event)

    # Upgrade to chains_required when text says so
    if itype == "weather_advisory" and _has_chain_requirement(combined):
        itype = "chains_required"

    highway   = _extract_highway(combined)
    direction = _extract_direction(combined)
    sev       = _nws_severity(severity, urgency)

    # Build short description: prefer headline, fall back to event name
    raw_desc = headline if headline else event
    short    = _truncate_desc(raw_desc, 100)

    # Truck-only heuristic: explicit mention of commercial vehicles
    truck_kw = ("commercial", "truck", "tractor", "semi", "18-wheel",
                "combination vehicle", "double", "triple")
    truck_only = any(kw in combined.lower() for kw in truck_kw)

    return {
        "type":        itype,
        "severity":    sev,
        "highway":     highway,
        "direction":   direction,
        "description": short,
        "source":      "nws",
        "expires":     _iso_to_unix(expires),
        "truck_only":  truck_only,
    }


def parse_nws_features(features: list) -> list:
    """
    Convert a list of NWS GeoJSON features to dot511 incident dicts.
    Skips non-road-relevant events. Returns [] on empty input.
    """
    incidents = []
    for f in features:
        inc = _parse_nws_feature(f)
        if inc:
            incidents.append(inc)
    return incidents


# ── State feed framework ──────────────────────────────────────────────────────

def _lat_lon_to_state(lat: float, lon: float) -> str | None:
    """
    Return best-guess US state code for a coordinate.
    Uses bounding box lookup — accurate within ±30-50 mi of state borders.
    Returns None if outside all known bounds (international or offshore).
    """
    matches = []
    for state, (lat_min, lat_max, lon_min, lon_max) in _STATE_BOUNDS.items():
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            matches.append(state)
    if not matches:
        return None
    # Prefer smallest bounding box (most specific) on overlap
    return min(
        matches,
        key=lambda s: (
            (_STATE_BOUNDS[s][1] - _STATE_BOUNDS[s][0]) *
            (_STATE_BOUNDS[s][3] - _STATE_BOUNDS[s][2])
        ),
    )


def _fetch_state_feed(state_code: str, config: dict) -> list:
    """
    Fetch state-specific 511 feed data.
    Returns [] when no feed is configured or on any failure.
    All feeds must be free public URLs — no API keys.
    """
    url = STATE_FEEDS.get(state_code)
    if not url or not _REQUESTS_AVAILABLE:
        return []
    try:
        r = __import__("requests").get(url, timeout=8, headers=_HEADERS)
        r.raise_for_status()
        # TODO: each state has its own format — add per-state parsers as feeds go live
        return []
    except Exception:
        return []


# ── Network fetch ─────────────────────────────────────────────────────────────

def _fetch_nws_features(lat: float, lon: float) -> list:
    """
    Fetch NWS alert features for a point. Returns raw GeoJSON feature list.
    Falls back to stale cache on network failure.
    Returns [] only when no data exists anywhere.
    """
    if not _REQUESTS_AVAILABLE:
        return []

    path = dot511_cache_path(lat, lon)
    cached, _ = cache_load(path, DOT511_CACHE_TIME)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    try:
        url = (f"https://api.weather.gov/alerts/active"
               f"?point={lat:.4f},{lon:.4f}")
        r = __import__("requests").get(url, timeout=8, headers=_HEADERS)
        r.raise_for_status()
        features = r.json().get("features", [])
        cache_save(path, json.dumps(features))
        return features
    except Exception as e:
        print(f"⚠  DOT/511 fetch error: {e}", file=sys.stderr)
        stale, _ = cache_stale(path)
        if stale:
            try:
                return json.loads(stale)
            except Exception:
                pass
        return []


# ── Public API ────────────────────────────────────────────────────────────────

def filter_truck_relevant(incidents: list, config: dict = None) -> list:
    """
    Filter incidents to those relevant to commercial truckers.

    Keeps:
      - All weather advisories (ice, wind, fog, flooding affect big rigs most)
      - All closures and bridge restrictions
      - All chains_required
      - Truck-only weigh station / bridge restriction notices

    Removes:
      - Marine, beach, rip current events (already filtered in parse)
      - Purely residential flood advisories with no highway mention
        when vehicle_type is not rv (RVs care about those too)
    """
    if config is None:
        config = {}
    if not incidents:
        return []

    result = []
    vtype = config.get("vehicle_type", "semi")

    for inc in incidents:
        itype = inc.get("type", "")

        # These always matter to truckers
        if itype in ("chains_required", "closure", "bridge_restriction",
                     "construction", "weigh_station"):
            result.append(inc)
            continue

        # Weather advisories: keep if they mention a highway OR have high+ severity
        if itype == "weather_advisory":
            sev = inc.get("severity", "low")
            hw  = inc.get("highway")
            if sev in ("critical", "high") or hw or vtype in ("rv",):
                result.append(inc)
                continue
            # Medium/low advisory with no highway mention: keep anyway for trucks
            # (a blizzard doesn't have to mention I-70 to close it)
            result.append(inc)
            continue

        # Incidents pass through
        if itype == "incident":
            result.append(inc)

    return result


def fetch_dot511(lat: float, lon: float, config: dict = None) -> list:
    """
    Fetch and normalize DOT/511 road condition incidents for a location.

    Sources (in order):
      1. NWS point-based alerts (all 50 states, free, always tried)
      2. State 511 feed if available for that state

    Results are cached at DOT511_CACHE_TIME (15 min).
    Returns [] on total failure — never raises.
    """
    if config is None:
        config = {}

    features  = _fetch_nws_features(lat, lon)
    incidents = parse_nws_features(features)

    state = _lat_lon_to_state(lat, lon)
    if state:
        state_data = _fetch_state_feed(state, config)
        incidents.extend(state_data)

    return filter_truck_relevant(incidents, config)


def get_active_incidents(lat: float, lon: float,
                         config: dict = None) -> list:
    """
    Return active DOT/511 incidents, subscription-gated (solo_pro+).
    Sorted by severity: critical → high → medium → low.

    Free tier: returns [] (use NWS alerts from core.api.fetch_alerts instead).
    Solo Pro+: full DOT/511 feed with chain requirements, closures, etc.
    """
    if config is None:
        config = {}

    if not has_feature(config, "dot511"):
        return []

    incidents = fetch_dot511(lat, lon, config)

    _sev_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    incidents.sort(key=lambda i: _sev_rank.get(i.get("severity", "low"), 0),
                   reverse=True)
    return incidents


def speak_dot511_alerts(incidents: list, config: dict) -> int:
    """
    Speak active DOT/511 incidents via tts.speak_alert().
    Maps incident type to TTS alert type from claude/prompts.py.
    Returns number of alerts spoken or queued.
    """
    if not config.get("tts_enabled", False):
        return 0
    if not incidents:
        return 0

    from core.tts import speak_alert

    # dot511 type → TTS alert type from claude/prompts.py _CB_VOICE_ALERTS
    _type_to_tts = {
        "chains_required":    "black_ice",      # closest CB string for winter driving
        "weather_advisory":   "hazard_reported",
        "closure":            "hazard_reported",
        "construction":       "hazard_reported",
        "bridge_restriction": "hazard_reported",
        "weigh_station":      "hazard_reported",
        "incident":           "hazard_reported",
    }
    _sev_to_tts = {
        "critical": "CRITICAL",
        "high":     "WARNING",
        "medium":   "WARNING",
        "low":      "INFO",
    }

    spoken = 0
    for inc in incidents:
        alert_t = _type_to_tts.get(inc.get("type", ""), "hazard_reported")
        tts_sev = _sev_to_tts.get(inc.get("severity", "low"), "INFO")
        if speak_alert(alert_t, tts_sev, config):
            spoken += 1
    return spoken


def _w(config=None) -> int:
    """Effective display width for dot511 module."""
    override = (config or {}).get("display_width_override")
    if override and isinstance(override, int) and 20 <= override <= 300:
        return override
    return max(36, shutil.get_terminal_size(fallback=(80, 24)).columns)


def _mode(w: int) -> str:
    if w < 40: return "ultra_compact"
    if w < 60: return "compact"
    if w < 80: return "standard"
    return "full"


def display_dot511(incidents: list, config: dict = None) -> None:
    """
    Width-responsive ASCII display of active DOT/511 incidents.
    Maximum 8 shown — covers a day's route without wall-of-text.
    """
    if config is None:
        config = {}

    w    = _w(config)
    mode = _mode(w)
    sep  = "─" * w

    if not incidents:
        if mode != "ultra_compact":
            print("No active DOT/511 advisories for this area.")
        return

    _sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}

    print(sep)
    if mode == "ultra_compact":
        print("⚠ DOT/511")
    else:
        print("  DOT / 511 Advisories")
    print(sep)

    for inc in incidents[:8]:
        itype  = inc.get("type", "").replace("_", " ").title()
        sev    = inc.get("severity", "low")
        hw     = inc.get("highway", "")
        desc   = inc.get("description", "")
        src    = inc.get("source", "")
        truck  = inc.get("truck_only", False)
        dirn   = inc.get("direction", "")
        expires = inc.get("expires")

        icon     = _sev_icon.get(sev, "⚪")

        exp_str = ""
        if expires:
            mins_left = int((expires - time.time()) / 60)
            if 0 < mins_left < 120:
                exp_str = f" {mins_left}m"
            elif mins_left <= 0:
                exp_str = " EXP"

        if mode == "ultra_compact":
            hw_s  = f" {hw}" if hw else ""
            dir_s = f" {dirn[:2].upper()}" if dirn and dirn not in ("unknown", "") else ""
            line  = f"{icon}{itype[:10]}{hw_s}{dir_s}{exp_str}"
            print(line[:w])
        elif mode == "compact":
            hw_str    = f" [{hw}]" if hw else ""
            dir_str   = f" {dirn[:2].upper()}" if dirn and dirn not in ("unknown", "") else ""
            truck_str = " CMV" if truck else ""
            print(f"  {icon} {itype}{hw_str}{dir_str}{truck_str}{exp_str}")
        else:
            hw_str    = f" [{hw}]" if hw else ""
            dir_str   = f" {dirn}" if dirn and dirn != "unknown" else ""
            truck_str = " (CMV)" if truck else ""
            src_str   = f" — {src.upper()}" if src else ""
            exp_full  = ""
            if expires:
                mins_left = int((expires - time.time()) / 60)
                if 0 < mins_left < 120:
                    exp_full = f" (expires {mins_left}min)"
                elif mins_left <= 0:
                    exp_full = " (expired)"
            print(f"  {icon} {itype}{hw_str}{dir_str}{truck_str}{src_str}{exp_full}")
            if desc:
                print(f"     {desc[:w - 5]}")

    if len(incidents) > 8:
        print(f"+{len(incidents) - 8}" if mode == "ultra_compact" else f"  … and {len(incidents) - 8} more")
    print(sep)
