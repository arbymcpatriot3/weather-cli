#!/usr/bin/env python3
# core/alerts.py — Clean Shot: road hazard alert engine
# Tiers: Free (NOAA only) | Solo Pro+ (all hazard types)
#
# Planned hazard types:
#   black_ice   — temp ≤ 34°F + recent precip, road surface model
#   fog         — visibility < 0.25 mi from METAR/NWS
#   flood       — NWS Flash Flood warnings + elevation model
#   high_wind   — gusts > threshold for vehicle type/height
#   diesel_gel  — temp < 15°F (B20 gels at 10°F, B5 at -5°F)
#
# CB radio style voice strings live in claude/prompts.py
# TTS playback is handled by core/tts.py

# TODO: implement in module sprint


HAZARD_TYPES = ("black_ice", "fog", "flood", "high_wind", "diesel_gel")


def get_road_alerts(lat: float, lon: float, parsed: dict,
                    tier: str = "free") -> list:
    """
    Evaluate road hazard alerts from parsed weather data.

    Args:
        lat, lon : current position
        parsed   : output of core.weather.build_parsed()
        tier     : subscription tier string

    Returns:
        list of alert dicts:
          { type, severity, message, cb_message, tts_text }
    """
    # TODO: implement hazard detection logic
    return []


def diesel_gel_risk(temp_f: float) -> str:
    """Return 'none' | 'watch' | 'warning' | 'emergency' based on temp."""
    if temp_f > 20:
        return "none"
    if temp_f > 15:
        return "watch"
    if temp_f > 5:
        return "warning"
    return "emergency"
