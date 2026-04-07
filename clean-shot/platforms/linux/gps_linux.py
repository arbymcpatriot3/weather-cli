#!/usr/bin/env python3
# platforms/linux/gps_linux.py — Clean Shot: Linux GPS via gpsd
# Supports USB/Bluetooth NMEA devices through gpsd daemon.
# Install: sudo apt install gpsd python3-gps
# TODO: implement in module sprint

def get_gps_linux() -> tuple:
    """
    Get current position from gpsd.
    Returns (lat, lon) or None if unavailable.
    """
    try:
        import gps
        session = gps.gps(mode=gps.WATCH_ENABLE | gps.WATCH_NEWSTYLE)
        for _ in range(10):  # try up to 10 packets
            report = session.next()
            if report["class"] == "TPV":
                lat = getattr(report, "lat", None)
                lon = getattr(report, "lon", None)
                if lat and lon:
                    session.close()
                    return lat, lon
        session.close()
    except Exception:
        pass
    return None
