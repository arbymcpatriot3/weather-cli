#!/usr/bin/env python3
# core/feedback.py — Clean Shot: driver hazard reports + community feed
# Tier: Free (submit) | Solo Pro+ (receive nearby reports)
#
# Report flow:
#   Driver types or speaks a report
#   → core/hazards.py / claude/parser.py normalizes it
#   → Compressed to < 200 bytes for 2G upload
#   → Server fans out to nearby drivers
#   → Claude clusters patterns (claude/patterns.py)
#
# Report types: black_ice | fog | accident | debris | construction |
#               weigh_station | parking_full | diesel_shortage | other
#
# TODO: implement in module sprint


REPORT_TYPES = (
    "black_ice", "fog", "accident", "debris", "construction",
    "weigh_station", "parking_full", "diesel_shortage", "other",
)


def submit_report(lat: float, lon: float, report_type: str,
                  notes: str = "", config: dict = None) -> bool:
    """
    Submit a community hazard report.
    Queues report for compressed upload. Stub.
    """
    # TODO: validate type, compress payload, queue for upload,
    #       increment config["reports_submitted"]
    return False


def get_feed(lat: float, lon: float,
             radius_miles: float = 25.0) -> list:
    """
    Fetch community reports near position.
    Returns list of report dicts. Stub.
    """
    return []


def upvote_report(report_id: str, config: dict = None) -> bool:
    """Confirm a community report is accurate. Stub."""
    return False


def dismiss_report(report_id: str, config: dict = None) -> bool:
    """Dismiss a community report (gone, resolved). Stub."""
    return False
