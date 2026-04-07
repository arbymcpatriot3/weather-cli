#!/usr/bin/env python3
# platforms/windows/gps_windows.py — Clean Shot: Windows Location API GPS
# Uses Windows.Devices.Geolocation via winrt bindings.
# Install: pip install winrt-Windows.Devices.Geolocation
# TODO: implement in module sprint

def get_gps_windows() -> tuple:
    """Get current position from Windows Location API. Returns (lat, lon) or None."""
    try:
        import asyncio
        import winrt.windows.devices.geolocation as geo

        async def _get():
            locator = geo.Geolocator()
            pos = await locator.get_geoposition_async()
            coord = pos.coordinate
            return coord.latitude, coord.longitude

        return asyncio.run(_get())
    except Exception:
        return None
