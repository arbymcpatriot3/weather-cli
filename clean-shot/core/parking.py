#!/usr/bin/env python3
from __future__ import annotations
# core/parking.py — Clean Shot: smart parking runway
# Tier: Solo Pro+ (smart_parking feature)
#
# The runway: miles you can legally drive before HOS forces a stop.
#   runway_miles = ((hos_drive_remaining_min - 15) / 60) × speed_mph
#   The 15-min buffer is conservative time to find and pull into a stop.
#
# HOS time source: config["hos_drive_remaining_min"]
#   Default 660 min (11 hours — full fresh property-carrying window).
#   Set by core/hos.py when that module is active.
#
# Speed source: config["speed_mph"]  (default 55 — conservative truck speed)
#   Updated by core/gps.py GPS polling when moving.
#
# Stop database (offline → online):
#   1. _EMBEDDED_STOPS — ~80 stops on 8 major US corridors (ships with app)
#   2. Overpass API (OpenStreetMap) — free, no key, 50-mi radius, cached 15 min
#   3. Community additions via core/hazards.py Phase 2
#
# TTS thresholds per trip (each fires once; call reset_announcements() at start):
#   120 min → INFO  "parking_ahead"   — start looking now
#    60 min → WARNING "parking_ahead"  — get serious
#    30 min → WARNING "hos_warning"    — you need to stop soon
#    15 min → CRITICAL "hos_warning"   — pull over NOW
#
# Data budget: Overpass response typically 5–15 KB for 50-mi radius. Under 50 KB.

import json
import shutil
import sys
import time
from pathlib import Path

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

from core.cache import (
    cache_load, cache_save, cache_stale,
    parking_cache_path, DOT511_CACHE_TIME,
)
from core.gps import haversine
from core.subscription import has_feature

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_SPEED_MPH      = 55.0   # conservative truck cruise speed
PARKING_BUFFER_MIN     = 15     # minutes reserved for finding + pulling into stop
HOD_DEFAULT_MIN        = 660    # 11 hours — full fresh HOS window (property)

# TTS thresholds: (minutes_remaining, tts_severity, alert_type)
_ANNOUNCE_THRESHOLDS = [
    (120, "INFO",     "parking_ahead"),   # 2 hours — start looking
    (60,  "WARNING",  "parking_ahead"),   # 1 hour  — get serious
    (30,  "WARNING",  "hos_warning"),     # 30 min  — need to stop soon
    (15,  "CRITICAL", "hos_warning"),     # 15 min  — pull over now
]

# Valid truck stop chains
CHAINS = ("pilot", "loves", "flyingj", "ta", "petro", "other")

# ── Module state — resets each trip ───────────────────────────────────────────
# Tracks which TTS thresholds have already fired so they announce only once.
_announced_thresholds: set = set()


# ── Embedded stop database — offline backbone ─────────────────────────────────
# ~80 stops across 8 major US corridors.
# Coordinates are approximate (±2–5 miles of actual stop location).
# amenities: fuel | showers | food | wifi | cat_scale | laundry
# spaces: None = unknown (real-time availability not yet integrated)
# rating: community rating 1.0–5.0; None = no ratings yet

_EMBEDDED_STOPS = [
    # ── I-40 East-West backbone ────────────────────────────────────────────────
    {"name": "Pilot #428",        "chain": "pilot",   "lat": 35.04, "lon": -90.18, "highway": "I-40", "exit": "1",   "state": "TN", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.2},
    {"name": "Love's #683",       "chain": "loves",   "lat": 35.04, "lon": -89.91, "highway": "I-40", "exit": "12",  "state": "TN", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 4.0},
    {"name": "Pilot #316",        "chain": "pilot",   "lat": 34.75, "lon": -92.30, "highway": "I-40", "exit": "135", "state": "AR", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.1},
    {"name": "Love's #412",       "chain": "loves",   "lat": 35.39, "lon": -94.40, "highway": "I-40", "exit": "7",   "state": "AR", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 3.9},
    {"name": "Love's #719",       "chain": "loves",   "lat": 35.46, "lon": -97.51, "highway": "I-40", "exit": "140", "state": "OK", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 4.0},
    {"name": "TA Oklahoma City",  "chain": "ta",      "lat": 35.42, "lon": -97.48, "highway": "I-40", "exit": "145", "state": "OK", "amenities": ["fuel","showers","food","wifi","cat_scale","laundry"], "spaces": None, "rating": 4.3},
    {"name": "Flying J #618",     "chain": "flyingj", "lat": 35.17, "lon": -101.97,"highway": "I-40", "exit": "60",  "state": "TX", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.0},
    {"name": "Pilot #511",        "chain": "pilot",   "lat": 35.22, "lon": -101.73,"highway": "I-40", "exit": "75",  "state": "TX", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.2},
    {"name": "Pilot #334",        "chain": "pilot",   "lat": 35.08, "lon": -106.65,"highway": "I-40", "exit": "155", "state": "NM", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.1},
    {"name": "Love's #531",       "chain": "loves",   "lat": 35.53, "lon": -108.74,"highway": "I-40", "exit": "20",  "state": "NM", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 3.8},
    {"name": "Pilot #219",        "chain": "pilot",   "lat": 35.20, "lon": -111.65,"highway": "I-40", "exit": "195", "state": "AZ", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.3},
    {"name": "Flying J #422",     "chain": "flyingj", "lat": 35.17, "lon": -111.60,"highway": "I-40", "exit": "198", "state": "AZ", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.1},
    {"name": "TA Kingman",        "chain": "ta",      "lat": 35.19, "lon": -113.95,"highway": "I-40", "exit": "53",  "state": "AZ", "amenities": ["fuel","showers","food","wifi","cat_scale","laundry"], "spaces": None, "rating": 4.0},
    {"name": "Pilot #178",        "chain": "pilot",   "lat": 34.90, "lon": -117.02,"highway": "I-40", "exit": "153", "state": "CA", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.2},

    # ── I-80 Northern east-west ────────────────────────────────────────────────
    {"name": "Pilot #509",        "chain": "pilot",   "lat": 41.60, "lon": -87.34, "highway": "I-80", "exit": "1",   "state": "IN", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.0},
    {"name": "Love's #614",       "chain": "loves",   "lat": 41.68, "lon": -86.25, "highway": "I-80", "exit": "77",  "state": "IN", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 3.9},
    {"name": "Flying J #318",     "chain": "flyingj", "lat": 41.57, "lon": -93.63, "highway": "I-80", "exit": "136", "state": "IA", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.2},
    {"name": "Pilot #417",        "chain": "pilot",   "lat": 41.60, "lon": -93.83, "highway": "I-80", "exit": "124", "state": "IA", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.1},
    {"name": "Love's #523",       "chain": "loves",   "lat": 41.26, "lon": -96.11, "highway": "I-80", "exit": "440", "state": "NE", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 4.0},
    {"name": "TA Omaha",          "chain": "ta",      "lat": 41.23, "lon": -95.93, "highway": "I-80", "exit": "449", "state": "NE", "amenities": ["fuel","showers","food","wifi","cat_scale","laundry"], "spaces": None, "rating": 4.3},
    {"name": "Pilot #266",        "chain": "pilot",   "lat": 41.12, "lon": -100.77,"highway": "I-80", "exit": "177", "state": "NE", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.1},
    {"name": "Flying J #511",     "chain": "flyingj", "lat": 41.13, "lon": -104.82,"highway": "I-80", "exit": "362", "state": "WY", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.0},
    {"name": "Love's #616",       "chain": "loves",   "lat": 41.12, "lon": -104.78,"highway": "I-80", "exit": "367", "state": "WY", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 3.9},
    {"name": "Pilot #388",        "chain": "pilot",   "lat": 41.27, "lon": -110.96,"highway": "I-80", "exit": "6",   "state": "WY", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.2},
    {"name": "TA Salt Lake City", "chain": "ta",      "lat": 40.72, "lon": -111.89,"highway": "I-80", "exit": "304", "state": "UT", "amenities": ["fuel","showers","food","wifi","cat_scale","laundry"], "spaces": None, "rating": 4.4},
    {"name": "Pilot #214",        "chain": "pilot",   "lat": 40.83, "lon": -115.76,"highway": "I-80", "exit": "301", "state": "NV", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.1},
    {"name": "Flying J #317",     "chain": "flyingj", "lat": 39.53, "lon": -119.81,"highway": "I-80", "exit": "12",  "state": "NV", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.0},

    # ── I-70 Central east-west ────────────────────────────────────────────────
    {"name": "Pilot #419",        "chain": "pilot",   "lat": 39.96, "lon": -82.85, "highway": "I-70", "exit": "112", "state": "OH", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.1},
    {"name": "Love's #712",       "chain": "loves",   "lat": 39.73, "lon": -86.28, "highway": "I-70", "exit": "59",  "state": "IN", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 4.0},
    {"name": "Flying J #614",     "chain": "flyingj", "lat": 39.69, "lon": -86.35, "highway": "I-70", "exit": "52",  "state": "IN", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.2},
    {"name": "TA St. Louis",      "chain": "ta",      "lat": 38.78, "lon": -90.44, "highway": "I-70", "exit": "10",  "state": "MO", "amenities": ["fuel","showers","food","wifi","cat_scale","laundry"], "spaces": None, "rating": 4.3},
    {"name": "Pilot #319",        "chain": "pilot",   "lat": 38.79, "lon": -90.41, "highway": "I-70", "exit": "14",  "state": "MO", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.1},
    {"name": "Love's #418",       "chain": "loves",   "lat": 38.85, "lon": -97.61, "highway": "I-70", "exit": "252", "state": "KS", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 3.9},
    {"name": "Pilot #272",        "chain": "pilot",   "lat": 39.40, "lon": -101.05,"highway": "I-70", "exit": "54",  "state": "KS", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.0},
    {"name": "Flying J #516",     "chain": "flyingj", "lat": 39.78, "lon": -104.87,"highway": "I-70", "exit": "285", "state": "CO", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.3},
    {"name": "Love's #611",       "chain": "loves",   "lat": 39.07, "lon": -108.55,"highway": "I-70", "exit": "26",  "state": "CO", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 4.0},

    # ── I-10 Southern east-west ────────────────────────────────────────────────
    {"name": "Pilot #314",        "chain": "pilot",   "lat": 30.34, "lon": -82.09, "highway": "I-10", "exit": "335", "state": "FL", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.2},
    {"name": "Love's #519",       "chain": "loves",   "lat": 30.66, "lon": -88.17, "highway": "I-10", "exit": "19",  "state": "AL", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 3.9},
    {"name": "Flying J #413",     "chain": "flyingj", "lat": 30.40, "lon": -91.18, "highway": "I-10", "exit": "163", "state": "LA", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.0},
    {"name": "Pilot #226",        "chain": "pilot",   "lat": 30.08, "lon": -94.10, "highway": "I-10", "exit": "847", "state": "TX", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.1},
    {"name": "TA Houston",        "chain": "ta",      "lat": 29.76, "lon": -95.21, "highway": "I-10", "exit": "766", "state": "TX", "amenities": ["fuel","showers","food","wifi","cat_scale","laundry"], "spaces": None, "rating": 4.4},
    {"name": "Love's #714",       "chain": "loves",   "lat": 29.42, "lon": -98.49, "highway": "I-10", "exit": "574", "state": "TX", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 4.0},
    {"name": "Pilot #318",        "chain": "pilot",   "lat": 31.04, "lon": -104.83,"highway": "I-10", "exit": "138", "state": "TX", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.2},
    {"name": "Flying J #512",     "chain": "flyingj", "lat": 31.76, "lon": -106.49,"highway": "I-10", "exit": "13",  "state": "TX", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.1},
    {"name": "TA Tucson",         "chain": "ta",      "lat": 32.22, "lon": -110.97,"highway": "I-10", "exit": "268", "state": "AZ", "amenities": ["fuel","showers","food","wifi","cat_scale","laundry"], "spaces": None, "rating": 4.3},
    {"name": "Pilot #417",        "chain": "pilot",   "lat": 33.45, "lon": -112.07,"highway": "I-10", "exit": "133", "state": "AZ", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.2},

    # ── I-95 East Coast ────────────────────────────────────────────────────────
    {"name": "Love's #618",       "chain": "loves",   "lat": 30.48, "lon": -81.71, "highway": "I-95", "exit": "362", "state": "FL", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 4.0},
    {"name": "Pilot #421",        "chain": "pilot",   "lat": 32.09, "lon": -81.10, "highway": "I-95", "exit": "94",  "state": "GA", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.2},
    {"name": "Love's #716",       "chain": "loves",   "lat": 34.20, "lon": -79.83, "highway": "I-95", "exit": "164", "state": "SC", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 3.9},
    {"name": "Flying J #314",     "chain": "flyingj", "lat": 35.93, "lon": -77.80, "highway": "I-95", "exit": "138", "state": "NC", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.1},
    {"name": "Love's #513",       "chain": "loves",   "lat": 37.23, "lon": -77.40, "highway": "I-95", "exit": "61",  "state": "VA", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 4.0},
    {"name": "TA Baltimore",      "chain": "ta",      "lat": 39.35, "lon": -76.62, "highway": "I-95", "exit": "62",  "state": "MD", "amenities": ["fuel","showers","food","wifi","cat_scale","laundry"], "spaces": None, "rating": 4.2},

    # ── I-35 North-South central ───────────────────────────────────────────────
    {"name": "Pilot #227",        "chain": "pilot",   "lat": 27.50, "lon": -99.51, "highway": "I-35", "exit": "3",   "state": "TX", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.1},
    {"name": "Love's #615",       "chain": "loves",   "lat": 29.42, "lon": -98.47, "highway": "I-35", "exit": "157", "state": "TX", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 4.0},
    {"name": "Flying J #419",     "chain": "flyingj", "lat": 30.25, "lon": -97.81, "highway": "I-35", "exit": "227", "state": "TX", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.2},
    {"name": "Pilot #314",        "chain": "pilot",   "lat": 31.56, "lon": -97.15, "highway": "I-35", "exit": "330", "state": "TX", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.1},
    {"name": "TA Dallas",         "chain": "ta",      "lat": 32.75, "lon": -97.33, "highway": "I-35", "exit": "438", "state": "TX", "amenities": ["fuel","showers","food","wifi","cat_scale","laundry"], "spaces": None, "rating": 4.3},
    {"name": "Love's #512",       "chain": "loves",   "lat": 35.55, "lon": -97.55, "highway": "I-35", "exit": "140", "state": "OK", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 3.9},
    {"name": "Pilot #318",        "chain": "pilot",   "lat": 37.69, "lon": -97.34, "highway": "I-35", "exit": "10",  "state": "KS", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.0},
    {"name": "Flying J #413",     "chain": "flyingj", "lat": 39.13, "lon": -94.58, "highway": "I-35", "exit": "15",  "state": "MO", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.2},
    {"name": "Love's #611",       "chain": "loves",   "lat": 42.03, "lon": -93.62, "highway": "I-35", "exit": "111", "state": "IA", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 4.0},
    {"name": "Pilot #516",        "chain": "pilot",   "lat": 44.98, "lon": -93.27, "highway": "I-35", "exit": "12",  "state": "MN", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.1},

    # ── I-90 Northern ────────────────────────────────────────────────────────
    {"name": "Pilot #419",        "chain": "pilot",   "lat": 42.88, "lon": -78.88, "highway": "I-90", "exit": "49",  "state": "NY", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.0},
    {"name": "Love's #514",       "chain": "loves",   "lat": 41.48, "lon": -81.80, "highway": "I-90", "exit": "177", "state": "OH", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 3.9},
    {"name": "Flying J #317",     "chain": "flyingj", "lat": 41.66, "lon": -83.56, "highway": "I-90", "exit": "4",   "state": "OH", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.1},
    {"name": "TA Gary",           "chain": "ta",      "lat": 41.62, "lon": -87.36, "highway": "I-90", "exit": "1",   "state": "IN", "amenities": ["fuel","showers","food","wifi","cat_scale","laundry"], "spaces": None, "rating": 4.2},
    {"name": "Pilot #316",        "chain": "pilot",   "lat": 43.07, "lon": -89.40, "highway": "I-90", "exit": "138", "state": "WI", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.2},
    {"name": "Love's #418",       "chain": "loves",   "lat": 43.54, "lon": -96.73, "highway": "I-90", "exit": "390", "state": "SD", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 4.0},
    {"name": "Flying J #512",     "chain": "flyingj", "lat": 44.07, "lon": -103.23,"highway": "I-90", "exit": "55",  "state": "SD", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.1},
    {"name": "Love's #613",       "chain": "loves",   "lat": 45.79, "lon": -108.51,"highway": "I-90", "exit": "446", "state": "MT", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 4.0},
    {"name": "TA Spokane",        "chain": "ta",      "lat": 47.66, "lon": -117.43,"highway": "I-90", "exit": "280", "state": "WA", "amenities": ["fuel","showers","food","wifi","cat_scale","laundry"], "spaces": None, "rating": 4.3},

    # ── I-65 Southeast ────────────────────────────────────────────────────────
    {"name": "Pilot #318",        "chain": "pilot",   "lat": 39.73, "lon": -86.28, "highway": "I-65", "exit": "119", "state": "IN", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.1},
    {"name": "Love's #416",       "chain": "loves",   "lat": 38.25, "lon": -85.76, "highway": "I-65", "exit": "15",  "state": "KY", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 3.9},
    {"name": "Flying J #614",     "chain": "flyingj", "lat": 36.17, "lon": -86.78, "highway": "I-65", "exit": "86",  "state": "TN", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.2},
    {"name": "TA Nashville",      "chain": "ta",      "lat": 36.15, "lon": -86.80, "highway": "I-65", "exit": "90",  "state": "TN", "amenities": ["fuel","showers","food","wifi","cat_scale","laundry"], "spaces": None, "rating": 4.4},
    {"name": "Love's #511",       "chain": "loves",   "lat": 33.52, "lon": -86.80, "highway": "I-65", "exit": "264", "state": "AL", "amenities": ["fuel","showers","food","wifi"],              "spaces": None, "rating": 3.8},
    {"name": "Pilot #214",        "chain": "pilot",   "lat": 30.69, "lon": -88.04, "highway": "I-65", "exit": "9",   "state": "AL", "amenities": ["fuel","showers","food","wifi","cat_scale"], "spaces": None, "rating": 4.0},
]


# ── Runway computation ────────────────────────────────────────────────────────

def compute_runway(config: dict) -> dict:
    """
    Compute how many miles the driver can legally travel before HOS forces a stop.

    Returns:
        {
            "miles":     float  — max drivable miles (0 if HOS exhausted)
            "minutes":   int    — HOS minutes remaining (raw, before buffer)
            "speed_mph": float  — speed used in calculation
            "urgent":    bool   — True if <= 60 min remaining
            "critical":  bool   — True if <= 30 min remaining
            "warning":   bool   — True if <= 120 min remaining
            "level":     str    — "normal" | "warning" | "urgent" | "critical"
        }
    """
    minutes  = max(0, int(config.get("hos_drive_remaining_min", HOD_DEFAULT_MIN)))
    speed    = float(config.get("speed_mph", DEFAULT_SPEED_MPH))
    speed    = max(1.0, speed)   # guard against 0 speed

    # Apply parking buffer — subtract time needed to find/pull into a stop
    effective_min = max(0, minutes - PARKING_BUFFER_MIN)
    miles         = round((effective_min / 60.0) * speed, 1)

    level    = _urgency_level(minutes)
    return {
        "miles":     miles,
        "minutes":   minutes,
        "speed_mph": speed,
        "urgent":    minutes <= 60,
        "critical":  minutes <= 30,
        "warning":   minutes <= 120,
        "level":     level,
    }


def _urgency_level(minutes: int) -> str:
    """Return human-readable urgency level from minutes remaining."""
    if minutes <= 30:   return "critical"
    if minutes <= 60:   return "urgent"
    if minutes <= 120:  return "warning"
    return "normal"


def format_runway_str(runway: dict) -> str:
    """
    Format runway info as a concise display string.
    e.g. "305 mi / 5h 30m" or "URGENT — 28 mi / 30m"
    """
    miles   = runway["miles"]
    minutes = runway["minutes"]
    hours   = minutes // 60
    mins    = minutes % 60

    time_str  = f"{hours}h {mins}m" if hours else f"{mins}m"
    miles_str = f"{miles:.0f} mi"

    prefix = {
        "critical": "URGENT — ",
        "urgent":   "URGENT — ",
        "warning":  "",
        "normal":   "",
    }.get(runway["level"], "")

    return f"{prefix}{miles_str} / {time_str}"


# ── Stop database ─────────────────────────────────────────────────────────────

def _load_embedded_stops() -> list:
    """Return the embedded stop list — always available offline."""
    return list(_EMBEDDED_STOPS)


def _fetch_overpass_stops(lat: float, lon: float,
                          radius_mi: float = 50.0) -> list:
    """
    Fetch truck stop nodes from OpenStreetMap Overpass API.
    Free, no key, returns stops within radius_mi.
    Parses chain name from OSM tags when available.
    Returns [] on network failure or if requests not available.
    """
    if not _REQUESTS_AVAILABLE:
        return []

    radius_m = int(radius_mi * 1609.34)
    query = (
        f"[out:json][timeout:15];"
        f'(node["amenity"="truck_stop"](around:{radius_m},{lat},{lon});'
        f'node["name"~"Pilot|Love\'s|Flying J|TA Petro|TravelCenters|Petro",'
        f'i](around:{radius_m},{lat},{lon}););'
        f"out body;"
    )
    try:
        r = _requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=15,
            headers={"User-Agent": "clean-shot/3.0 (bluecollarnation@proton.me)"},
        )
        r.raise_for_status()
        elements = r.json().get("elements", [])
        return [_overpass_node_to_stop(e) for e in elements
                if _overpass_node_to_stop(e)]
    except Exception:
        return []


def _overpass_node_to_stop(node: dict) -> dict | None:
    """Convert an Overpass node to a TruckStop dict. Returns None if unusable."""
    tags = node.get("tags", {})
    lat  = node.get("lat")
    lon  = node.get("lon")
    if lat is None or lon is None:
        return None

    name  = tags.get("name", "Truck Stop")
    chain = _detect_chain(name)

    amenities = []
    if tags.get("fuel") == "yes"    or tags.get("amenity") == "fuel":
        amenities.append("fuel")
    if tags.get("shower") == "yes":
        amenities.append("showers")
    if tags.get("restaurant") or tags.get("fast_food"):
        amenities.append("food")
    if tags.get("internet_access") in ("wlan", "yes"):
        amenities.append("wifi")
    if tags.get("truck_scale") == "yes":
        amenities.append("cat_scale")
    if not amenities:
        amenities = ["fuel"]   # assume at minimum

    return {
        "name":      name,
        "chain":     chain,
        "lat":       lat,
        "lon":       lon,
        "highway":   tags.get("ref:highway") or tags.get("highway"),
        "exit":      tags.get("exit"),
        "state":     None,   # OSM doesn't reliably have state codes
        "amenities": amenities,
        "spaces":    None,
        "rating":    None,
        "source":    "osm",
    }


def _detect_chain(name: str) -> str:
    """Detect chain brand from stop name string."""
    n = name.lower()
    if "pilot"    in n:                          return "pilot"
    if "love"     in n:                          return "loves"
    if "flying j" in n or "flyingj" in n:        return "flyingj"
    if "ta petro" in n or "travelcenter" in n:   return "ta"
    if "petro"    in n:                          return "petro"
    return "other"


def get_all_stops(lat: float, lon: float,
                  radius_mi: float = 50.0,
                  config: dict = None) -> list:
    """
    Return all truck stops within radius_mi: embedded + Overpass (cached).
    Deduplicates by proximity (stops within 0.5 mi of each other → keep one).
    """
    if config is None:
        config = {}

    stops = _load_embedded_stops()

    # Try live Overpass fetch (or serve from cache)
    cache_path = parking_cache_path(lat, lon)
    cached, _  = cache_load(cache_path, DOT511_CACHE_TIME)
    if cached:
        try:
            stops.extend(json.loads(cached))
        except Exception:
            pass
    else:
        live = _fetch_overpass_stops(lat, lon, radius_mi)
        if live:
            try:
                cache_save(cache_path, json.dumps(live))
            except Exception:
                pass
            stops.extend(live)

    return stops


def get_nearby_stops(lat: float, lon: float,
                     radius_miles: float = 50.0,
                     config: dict = None) -> list:
    """
    Return truck stops within radius_miles of (lat, lon), sorted closest first.
    Each stop gets a "distance_mi" key added.
    """
    if config is None:
        config = {}

    stops  = get_all_stops(lat, lon, radius_miles, config)
    nearby = []

    for s in stops:
        try:
            dist = haversine(lat, lon, s["lat"], s["lon"])
        except Exception:
            continue
        if dist <= radius_miles:
            entry = dict(s)
            entry["distance_mi"] = round(dist, 1)
            nearby.append(entry)

    nearby.sort(key=lambda s: s["distance_mi"])
    return nearby


def get_stops_in_corridor(lat: float, lon: float,
                          config: dict = None) -> list:
    """
    Return truck stops reachable within the driver's remaining HOS runway.
    These are the stops the driver MUST choose from before being forced to park.
    """
    if config is None:
        config = {}

    runway = compute_runway(config)
    if runway["miles"] <= 0:
        return []

    return get_nearby_stops(lat, lon, radius_miles=runway["miles"], config=config)


def find_recommended_stop(lat: float, lon: float,
                           config: dict = None) -> dict | None:
    """
    Return the best (closest) truck stop in the driver's HOS corridor.
    Returns None if no stops are reachable or position is unknown.
    """
    if config is None:
        config = {}
    if lat is None or lon is None:
        return None

    stops = get_stops_in_corridor(lat, lon, config)
    return stops[0] if stops else None


def filter_by_amenity(stops: list, required: list) -> list:
    """
    Return stops that have ALL of the required amenities.
    e.g. filter_by_amenity(stops, ["showers", "cat_scale"])
    """
    return [s for s in stops
            if all(a in s.get("amenities", []) for a in required)]


# ── TTS threshold system ──────────────────────────────────────────────────────

def reset_announcements() -> None:
    """
    Clear the announced-threshold tracker.
    Call this when the driver starts a new trip or resets HOS.
    """
    _announced_thresholds.clear()


def check_runway_thresholds(config: dict) -> tuple | None:
    """
    Check if the current HOS runway has newly crossed a TTS threshold.
    Returns (threshold_minutes, severity, alert_type) for the highest-priority
    new threshold crossed, or None if nothing new.

    Pure check — does NOT modify _announced_thresholds.
    Caller decides whether to announce; use announce_runway() for combined check+speak.
    """
    minutes = int(config.get("hos_drive_remaining_min", HOD_DEFAULT_MIN))

    for threshold, severity, alert_type in sorted(
            _ANNOUNCE_THRESHOLDS, key=lambda t: t[0]):  # lowest first
        if minutes <= threshold and threshold not in _announced_thresholds:
            return (threshold, severity, alert_type)
    return None


def announce_runway(config: dict) -> bool:
    """
    Check HOS runway thresholds and speak via TTS if a new one was just crossed.

    Returns True if an announcement was made.
    Marks the threshold as announced so it won't fire again this trip.
    Silently returns False if TTS is disabled.
    """
    result = check_runway_thresholds(config)
    if not result:
        return False

    threshold, severity, alert_type = result
    _announced_thresholds.add(threshold)

    if not config.get("tts_enabled", False):
        return False

    from core.tts import speak_alert
    force = (severity == "CRITICAL")
    return speak_alert(alert_type, severity, config, force=force)


# ── Display ───────────────────────────────────────────────────────────────────

def _w(config=None) -> int:
    """Effective display width for parking module."""
    override = (config or {}).get("display_width_override")
    if override and isinstance(override, int) and 20 <= override <= 300:
        return override
    return max(36, shutil.get_terminal_size(fallback=(80, 24)).columns)


def _mode(w: int) -> str:
    if w < 40: return "ultra_compact"
    if w < 60: return "compact"
    if w < 80: return "standard"
    return "full"


def display_stop(stop: dict, config: dict = None) -> None:
    """Width-responsive ASCII display of a single truck stop."""
    if config is None:
        config = {}

    w    = _w(config)
    mode = _mode(w)

    name      = stop.get("name", "Unknown Stop")
    chain     = stop.get("chain", "other").upper()
    dist      = stop.get("distance_mi", "?")
    hw        = stop.get("highway", "")
    exit_num  = stop.get("exit", "")
    amenities = stop.get("amenities", [])
    spaces    = stop.get("spaces")
    rating    = stop.get("rating")
    state     = stop.get("state", "")

    dist_str  = f"{dist:.1f}mi" if isinstance(dist, (int, float)) else str(dist)
    amenity_icons = {
        "fuel": "⛽", "showers": "🚿", "food": "🍔",
        "wifi": "📶", "cat_scale": "⚖️", "laundry": "👕",
    }
    icons = "".join(amenity_icons.get(a, "") for a in amenities)

    if mode == "ultra_compact":
        # Single line: dist NAME [chain]
        nm   = name[:12]
        line = f"{dist_str} {nm} [{chain[:2]}]"
        print(line[:w])
    elif mode == "compact":
        hw_s = f" {hw}" if hw else ""
        print(f"  {dist_str} {name[:20]}{hw_s} [{chain}]")
        if icons:
            print(f"    {icons}")
    else:
        hw_str    = f" [{hw} Exit {exit_num}]" if hw and exit_num else (f" [{hw}]" if hw else "")
        state_str = f" {state}" if state else ""
        spaces_s  = f" — {spaces} spaces" if spaces is not None else ""
        rating_s  = f" ★{rating:.1f}" if rating is not None else ""
        print(f"  {name}{state_str}{hw_str}{spaces_s}{rating_s}")
        print(f"    {dist_str} away  [{chain}]  {icons}")


def display_parking_status(lat: float, lon: float, config: dict) -> None:
    """
    Width-responsive runway status + corridor stops display.
    Shows urgency banner, runway distance/time, and top 5 stops in corridor.
    """
    if not has_feature(config, "smart_parking"):
        print("⚡ Smart Parking: Solo Pro+ required")
        return

    w      = _w(config)
    mode   = _mode(w)
    sep    = "─" * w
    runway = compute_runway(config)
    level  = runway["level"]

    print(sep)

    if mode == "ultra_compact":
        icons = {"critical": "⛔", "urgent": "🟠", "warning": "🟡", "ok": "🟢"}
        print(f"{icons.get(level,'•')} {format_runway_str(runway)}"[:w])
    elif mode == "compact":
        if level == "critical":
            print("  ⛔ STOP SOON — HOS EXPIRING")
        elif level == "urgent":
            print("  🟠 FIND PARKING — <1h left")
        elif level == "warning":
            print("  🟡 Start Looking — <2h left")
        else:
            print("  🟢 Parking Runway")
        print(f"  {format_runway_str(runway)}")
    else:
        if level == "critical":
            print("  ⛔ YOU MUST STOP SOON — HOS EXPIRING")
        elif level == "urgent":
            print("  🟠 FIND PARKING — Under 1 hour remaining")
        elif level == "warning":
            print("  🟡 Start Looking — Under 2 hours remaining")
        else:
            print("  🟢 Parking Runway")
        print(f"  Runway: {format_runway_str(runway)}")

    if lat is None or lon is None:
        if mode != "ultra_compact":
            print("  (No position — connect GPS for stop list)")
        print(sep)
        return

    stops = get_stops_in_corridor(lat, lon, config)

    if not stops:
        if mode != "ultra_compact":
            print("  No truck stops found in your remaining runway.")
    else:
        if mode == "ultra_compact":
            for stop in stops[:3]:
                display_stop(stop, config)
        else:
            print(f"  {len(stops)} stop{'s' if len(stops) != 1 else ''} in corridor:")
            if mode != "compact":
                print()
            for stop in stops[:5]:
                display_stop(stop, config)
                if mode != "compact":
                    print()

    if len(stops) > 5:
        print(f"+{len(stops)-5}" if mode == "ultra_compact" else f"  … and {len(stops) - 5} more stops in range")

    print(sep)
