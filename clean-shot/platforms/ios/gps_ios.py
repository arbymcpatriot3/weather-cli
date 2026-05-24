#!/usr/bin/env python3
# platforms/ios/gps_ios.py — Clean Shot: iOS CoreLocation bridge
# Uses Pythonista objc_util or Pyto's location module.
# TODO: implement in module sprint

def get_gps_ios() -> tuple:
    """Get current position from CoreLocation. Returns (lat, lon) or None."""
    try:
        # Pythonista path
        import location
        location.start_updates()
        import time; time.sleep(1)
        loc = location.get_location()
        location.stop_updates()
        if loc:
            return loc["latitude"], loc["longitude"]
    except Exception:
        pass

    try:
        # Pyto path
        from pyto import location as pyloc
        pos = pyloc.get_location()
        if pos:
            return pos.latitude, pos.longitude
    except Exception:
        pass

    return None
