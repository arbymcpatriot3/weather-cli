#!/usr/bin/env python3
# core/hazards.py — Clean Shot: community hazard reports + GPS clustering
# Tier: Solo Pro+ (community_hazards feature)
#
# Data flow:
#   Driver submits report (text or structured type)
#   → claude/parser.py parses free text → structured dict
#   → Stored locally at HAZARD_STORE_PATH (< 200 bytes per report)
#   → Queued for backend sync (stub — Phase 2)
#   → get_nearby_hazards() filters by distance + age + cleared
#   → cluster_reports() groups by proximity + type
#   → get_active_hazards() combines both; subscription-gated
#   → speak_nearby_hazards() routes to tts.speak_alert()
#
# Single hazard report budget: < 200 bytes (JSON over 2G)
# Example: {"t":"black_ice","lat":35.12,"lon":-90.01,"ts":1712345678,
#            "sev":"high","dir":"northbound","src":"community","clr":false,"note":"ice on bridge"}
#
# Cluster thresholds (module-level, overridable for tests):
#   CLUSTER_MIN_REPORTS = 2     min reports to flag as a cluster
#   CLUSTER_RADIUS_MI   = 10.0  geo radius ("same area")
#   CLUSTER_WINDOW_MIN  = 60    time window for clustering (minutes)
#   MAX_HAZARD_AGE_H    = 4     expire reports older than this

import json
import tempfile
import time
from pathlib import Path

from claude.parser import parse_hazard_report
from core.gps import haversine
from core.subscription import has_feature

# ── Constants ─────────────────────────────────────────────────────────────────

CLUSTER_MIN_REPORTS = 2       # 2 = meaningful signal even on a new platform
CLUSTER_RADIUS_MI   = 10.0    # geo radius to consider "same area"
CLUSTER_WINDOW_MIN  = 60      # time window for clustering (minutes)
MAX_HAZARD_AGE_H    = 4       # expire reports older than 4 hours

# Local flat-file store in the platform temp dir (survives app restarts, not reboots — intentional)
HAZARD_STORE_PATH = Path(tempfile.gettempdir()) / "clean-shot-cache" / "hazards_community.json"

# Map hazard report types → TTS alert types in claude/prompts.py _CB_VOICE_ALERTS
_HAZARD_TO_ALERT = {
    "black_ice":       "black_ice",
    "fog":             "fog",
    "flood":           "flood",
    "accident":        "hazard_reported",
    "debris":          "hazard_reported",
    "construction":    "hazard_reported",
    "weigh_station":   "hazard_reported",
    "parking_full":    "parking_ahead",
    "diesel_shortage": "hazard_reported",
    "other":           "hazard_reported",
}

# Map hazard severity strings → TTS severity levels
_SEV_TO_TTS = {
    "critical": "CRITICAL",
    "high":     "WARNING",
    "medium":   "WARNING",
    "low":      "INFO",
}


# ── Local store helpers ────────────────────────────────────────────────────────

def _load_local_store() -> list:
    """Load locally-stored hazard reports. Returns [] on any error."""
    if not HAZARD_STORE_PATH.exists():
        return []
    try:
        return json.loads(HAZARD_STORE_PATH.read_text())
    except Exception:
        return []


def _save_local_store(reports: list) -> None:
    """Atomic write of hazard store (tmp → rename)."""
    HAZARD_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = HAZARD_STORE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(reports))
    tmp.rename(HAZARD_STORE_PATH)


def clear_local_store() -> None:
    """Erase all locally stored hazard reports. Used in tests and factory reset."""
    _save_local_store([])


# ── Report construction ────────────────────────────────────────────────────────

def _make_report(lat: float, lon: float, parsed: dict,
                 source: str = "community") -> dict:
    """
    Build a compact hazard report dict.
    Target: < 200 bytes when serialized.
    """
    return {
        "t":   parsed.get("type", "other"),
        "lat": round(lat, 4),
        "lon": round(lon, 4),
        "ts":  int(time.time()),
        "sev": parsed.get("severity", "medium"),
        "dir": parsed.get("direction", "unknown"),
        "src": source,
        "clr": bool(parsed.get("cleared", False)),
        "note": (parsed.get("notes") or "")[:50],
    }


def _serialize_report(report: dict) -> str:
    """Compact JSON string. Must stay under 200 bytes."""
    return json.dumps(report, separators=(",", ":"))


# ── Public API ────────────────────────────────────────────────────────────────

def submit_hazard(lat: float, lon: float,
                  hazard_type: str = "",
                  description: str = "",
                  config: dict = None) -> bool:
    """
    Submit a community hazard report at the driver's current coordinates.

    Args:
        lat, lon     : report location
        hazard_type  : pre-classified type (optional — overrides parsed type)
        description  : free-text report (parsed by claude/parser.py offline)
        config       : driver config dict

    Returns True if report was stored.
    """
    if config is None:
        config = {}

    parsed = parse_hazard_report(description, config.get("claude_api_key"))
    if hazard_type:
        parsed["type"] = hazard_type

    report = _make_report(lat, lon, parsed)

    # Enforce 200-byte data budget — trim note until it fits
    serialized = _serialize_report(report)
    while len(serialized.encode()) > 200 and report["note"]:
        report["note"] = report["note"][:-1]
        serialized = _serialize_report(report)

    reports = _load_local_store()
    reports.append(report)
    _save_local_store(reports)

    # Backend sync stub (Phase 2 — offline-sync buffer → POST to BCN API)
    _sync_to_backend(report, config)

    return True


def get_nearby_hazards(lat: float, lon: float,
                       radius_miles: float = 25.0,
                       config: dict = None) -> list:
    """
    Return active hazard reports within radius_miles of (lat, lon).

    Filters:
      - Within radius_miles
      - Not older than MAX_HAZARD_AGE_H hours
      - Not marked cleared (clr=True)
      - Sorted closest first

    Does NOT require subscription — callers that need gating use get_active_hazards().
    """
    if config is None:
        config = {}

    reports = _load_local_store()
    nearby  = []

    for r in reports:
        try:
            dist = haversine(lat, lon, r["lat"], r["lon"])
        except Exception:
            continue

        if dist > radius_miles:
            continue
        if (time.time() - r.get("ts", 0)) / 3600 > MAX_HAZARD_AGE_H:
            continue
        if r.get("clr", False):
            continue

        entry = dict(r)
        entry["distance_mi"] = round(dist, 2)
        nearby.append(entry)

    nearby.sort(key=lambda r: r["distance_mi"])
    return nearby


def expire_old_hazards(reports: list) -> list:
    """
    Return only reports younger than MAX_HAZARD_AGE_H hours.
    Operates on an in-memory list — does not write to disk.
    """
    cutoff = time.time() - MAX_HAZARD_AGE_H * 3600
    return [r for r in reports if r.get("ts", 0) >= cutoff]


def cluster_reports(reports: list) -> list:
    """
    Group nearby reports of the same type into clusters.

    Rules:
      - Only considers reports within CLUSTER_WINDOW_MIN minutes
      - Groups reports within CLUSTER_RADIUS_MI of each other (by type)
      - Only emits clusters with >= CLUSTER_MIN_REPORTS members
      - Uses worst (highest) severity across the cluster

    Returns list of cluster dicts:
      {hazard_type, center_lat, center_lon, driver_count, severity, reports}
    """
    if not reports:
        return []

    cutoff = time.time() - CLUSTER_WINDOW_MIN * 60
    recent = [r for r in reports if r.get("ts", 0) >= cutoff]

    # Group by hazard type
    by_type: dict = {}
    for r in recent:
        by_type.setdefault(r.get("t", "other"), []).append(r)

    _sev_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    clusters  = []

    for htype, group in by_type.items():
        visited = [False] * len(group)

        for i, anchor in enumerate(group):
            if visited[i]:
                continue

            members   = [anchor]
            visited[i] = True

            for j, other in enumerate(group):
                if visited[j]:
                    continue
                try:
                    d = haversine(anchor["lat"], anchor["lon"],
                                  other["lat"],  other["lon"])
                except Exception:
                    continue
                if d <= CLUSTER_RADIUS_MI:
                    members.append(other)
                    visited[j] = True

            if len(members) < CLUSTER_MIN_REPORTS:
                continue

            center_lat = round(sum(r["lat"] for r in members) / len(members), 4)
            center_lon = round(sum(r["lon"] for r in members) / len(members), 4)
            worst_sev  = max(
                (r.get("sev", "medium") for r in members),
                key=lambda s: _sev_rank.get(s, 0),
            )

            clusters.append({
                "hazard_type":  htype,
                "center_lat":   center_lat,
                "center_lon":   center_lon,
                "driver_count": len(members),
                "severity":     worst_sev,
                "reports":      members,
            })

    return clusters


def get_active_hazards(lat: float, lon: float,
                       config: dict = None) -> list:
    """
    Return nearby hazards and clusters, subscription-gated (solo_pro+).

    Clustered hazard types replace their individual reports in the result.
    Returns list sorted by distance, closest first.
    Each item has at least: {t or hazard_type, distance_mi, sev or severity}
    """
    if config is None:
        config = {}

    if not has_feature(config, "community_hazards"):
        return []

    nearby   = get_nearby_hazards(lat, lon, config=config)
    clusters = cluster_reports(nearby)

    cluster_types = {c["hazard_type"] for c in clusters}
    result = []

    for c in clusters:
        try:
            dist = haversine(lat, lon, c["center_lat"], c["center_lon"])
        except Exception:
            dist = 0.0
        c["distance_mi"] = round(dist, 2)
        result.append(c)

    for r in nearby:
        if r.get("t") not in cluster_types:
            result.append(r)

    result.sort(key=lambda x: x.get("distance_mi", 999))
    return result


def parse_hazard_text(text: str, config: dict = None) -> dict:
    """
    Parse free-text hazard description → structured dict.
    Delegates to claude/parser.py (keyword fallback always available offline).
    """
    if config is None:
        config = {}
    return parse_hazard_report(text, config.get("claude_api_key"))


def hazard_to_alert_type(hazard_type: str) -> str:
    """Map a hazard report type to a TTS alert type from claude/prompts.py."""
    return _HAZARD_TO_ALERT.get(hazard_type, "hazard_reported")


def severity_to_tts(sev_str: str) -> str:
    """Map hazard severity string ('high', 'critical', etc.) to TTS severity level."""
    return _SEV_TO_TTS.get(sev_str.lower(), "INFO")


def speak_nearby_hazards(hazards: list, config: dict) -> int:
    """
    Speak nearby/active hazard alerts via tts.speak_alert().
    Uses distance_mi for severity escalation when available.
    Returns number of alerts dispatched or queued.
    """
    if not config.get("tts_enabled", False):
        return 0
    if not hazards:
        return 0

    from core.tts import speak_alert

    spoken = 0
    for h in hazards:
        htype    = h.get("t") or h.get("hazard_type", "other")
        sev_str  = h.get("sev") or h.get("severity", "medium")
        dist_mi  = h.get("distance_mi")
        alert_t  = hazard_to_alert_type(htype)
        tts_sev  = severity_to_tts(sev_str)
        if speak_alert(alert_t, tts_sev, config, distance_mi=dist_mi):
            spoken += 1
    return spoken


def display_hazards(hazards: list, config: dict = None) -> None:
    """
    ASCII display of nearby/active hazards.
    Maximum 5 shown — driver glance, not a report.
    """
    if config is None:
        config = {}

    if not hazards:
        print("No active community hazards nearby.")
        return

    print("─" * 45)
    print("  Community Hazards")
    print("─" * 45)

    for h in hazards[:5]:
        htype     = (h.get("t") or h.get("hazard_type", "other")).replace("_", " ").title()
        dist_mi   = h.get("distance_mi", "?")
        sev       = (h.get("sev") or h.get("severity", "medium")).upper()
        count     = h.get("driver_count", 1)
        note      = h.get("note", "")
        direction = h.get("dir", "")

        dist_str  = f"{dist_mi:.1f} mi" if isinstance(dist_mi, (int, float)) else str(dist_mi)
        count_str = f" ({count} drivers)" if count > 1 else ""
        dir_str   = f" [{direction}]" if direction and direction not in ("unknown", "") else ""
        note_str  = f"\n    {note}" if note else ""

        print(f"  [{sev}] {htype}{count_str} — {dist_str}{dir_str}{note_str}")

    if len(hazards) > 5:
        print(f"  ... and {len(hazards) - 5} more")
    print("─" * 45)


# ── Backend sync stub (Phase 2) ────────────────────────────────────────────────

def _sync_to_backend(report: dict, config: dict) -> bool:
    """
    Queue report for backend sync. Phase 2 stub.
    Full implementation: compress report, add to offline-sync buffer,
    POST to Blue Collar Nation API when connected.
    Budget: < 200 bytes per POST, < 5 KB/hr background.
    """
    # TODO: Phase 2 — BCN backend integration
    return False
