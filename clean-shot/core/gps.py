#!/usr/bin/env python3
# core/gps.py — Clean Shot: GPS + geo-confirm dispatcher
# Routes to platform-specific GPS:
#   Linux:   platforms/linux/gps_linux.py   (gpsd / serial NMEA)
#   Windows: platforms/windows/gps_windows.py (Windows Location API)
#   iOS:     platforms/ios/gps_ios.py        (CoreLocation bridge)
#
# Geo-confirm: verifies that weather data matches driver's actual location,
# not a stale cached position from hours ago.
#
# Offline fallback: last known GPS position stored in config.
# TODO: implement in module sprint

import platform


def get_position(config: dict) -> tuple:
    """
    Get current GPS position.
    Returns (lat, lon) or (None, None) if GPS unavailable.
    Falls back to config["latitude"], config["longitude"].
    """
    plat = platform.system().lower()

    try:
        if plat == "linux":
            from platforms.linux.gps_linux import get_gps_linux
            pos = get_gps_linux()
            if pos:
                return pos
        elif plat == "windows":
            from platforms.windows.gps_windows import get_gps_windows
            pos = get_gps_windows()
            if pos:
                return pos
    except Exception:
        pass

    # Fallback to last known position
    lat = config.get("latitude")
    lon = config.get("longitude")
    if lat and lon:
        return lat, lon
    return None, None


def update_position(config: dict) -> dict:
    """
    Refresh config with current GPS position if available.
    Returns updated config.
    """
    lat, lon = get_position(config)
    if lat and lon:
        config["latitude"]  = lat
        config["longitude"] = lon
    return config
