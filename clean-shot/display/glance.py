#!/usr/bin/env python3
# display/glance.py — Clean Shot: 2-second glance mode
# Designed for a quick look while stopped at a light or fuel stop.
# Single-screen, no scrolling. Max 6 lines. Largest text possible.
#
# Shows: temp | condition | wind | top hazard | HOS remaining | next parking
# ASCII + emoji only. Works on 40-column displays (CB radio head units).
#
# TODO: implement in module sprint


def display_glance(parsed: dict, hos_status: dict = None,
                   alerts: list = None, width: int = 80):
    """
    Render 2-second glance view.
    All critical info on a single screen with no scrolling. Stub.
    """
    cur  = parsed.get("current", {})
    city = parsed.get("city", "---")
    temp = cur.get("temp", 0)
    desc = cur.get("desc_short", "---")
    wind = cur.get("wind_speed", 0)

    # TODO: style for max readability at a glance
    print(f"  {city}")
    print(f"  {temp:.0f}°F  {desc}")
    print(f"  Wind {wind:.0f} mph")
    if alerts:
        print(f"  ⚠ {alerts[0].get('event', 'Alert')}")
    if hos_status:
        mins = hos_status.get("drive_remaining_min", 0)
        print(f"  HOS {mins//60}h {mins%60}m left")
