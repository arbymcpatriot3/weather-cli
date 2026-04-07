#!/usr/bin/env python3
# core/parking.py — Clean Shot: smart parking runway
# Tier: Solo Pro+
#
# "Runway" concept: how many miles of drivable time remain on current HOS
# before needing to park, so driver can plan the next safe parking spot.
#
# Data sources:
#   - Truck parking availability (FHWA TPAS / state DOT feeds)
#   - Rest area locations (static dataset, ships with app)
#   - Weigh station locations (static dataset)
#   - Community-reported parking tips (via core/feedback.py)
#
# TODO: implement in module sprint


def get_parking_runway(lat: float, lon: float,
                       hos_remaining_minutes: int,
                       avg_speed_mph: float = 55.0) -> dict:
    """
    Calculate how far the driver can go before needing to stop.
    Returns runway info dict. Stub.
    """
    # TODO: miles_remaining = (hos_remaining_minutes / 60) * avg_speed_mph
    #       find nearest parking within that range
    return {}


def find_truck_parking(lat: float, lon: float,
                       max_miles: float = 50.0) -> list:
    """
    Find available truck parking within max_miles.
    Returns list of parking location dicts. Stub.
    """
    return []


def find_rest_areas(lat: float, lon: float,
                    max_miles: float = 50.0) -> list:
    """Return rest areas near position. Stub."""
    return []
