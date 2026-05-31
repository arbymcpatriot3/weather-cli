#!/usr/bin/env python3
# core/hazard_logger.py — Clean Shot: fire-and-forget hazard logging to the Worker.
#
# Called after every hazard shown to the driver.
# Never crashes the app — all exceptions are silently swallowed.
#
# Usage:
#   from core.hazard_logger import log_hazard, log_session
#   log_hazard(config, "black_ice", "critical", state="PA", route="I-81")

from __future__ import annotations
import json
import threading

try:
    import requests as _requests
    _OK = True
except ImportError:
    _OK = False

from core.config import WORKER_URL

_LICENSE_HEADER = "X-License-Key"


def _license_key(config: dict) -> str:
    return str(config.get("license_key") or "").strip()


def log_hazard(
    config: dict,
    hazard_type: str,
    severity: str,
    state: str | None = None,
    route: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    acknowledged: int = 1,
) -> None:
    """Fire-and-forget: log a detected hazard to the Worker."""
    key = _license_key(config)
    if not key or not _OK:
        return

    payload = {
        "hazard_type":  hazard_type,
        "severity":     severity,
        "acknowledged": acknowledged,
    }
    if state:       payload["state"]  = state
    if route:       payload["route"]  = route
    if lat is not None: payload["lat"] = lat
    if lon is not None: payload["lon"] = lon

    threading.Thread(
        target=_post,
        args=(f"{WORKER_URL}/v1/hazard/log", payload, key),
        daemon=True,
    ).start()


def log_session(
    config: dict,
    queries: int = 0,
    hazards_detected: int = 0,
    states_checked: list[str] | None = None,
    miles_covered: float | None = None,
    session_start: int | None = None,
) -> None:
    """Fire-and-forget: log a completed session to the Worker."""
    key = _license_key(config)
    if not key or not _OK:
        return

    payload: dict = {
        "queries":          queries,
        "hazards_detected": hazards_detected,
        "states_checked":   states_checked or [],
    }
    if miles_covered is not None: payload["miles_covered"]  = miles_covered
    if session_start  is not None: payload["session_start"] = session_start

    threading.Thread(
        target=_post,
        args=(f"{WORKER_URL}/v1/session/log", payload, key),
        daemon=True,
    ).start()


def _post(url: str, payload: dict, license_key: str) -> None:
    try:
        _requests.post(
            url,
            json=payload,
            headers={_LICENSE_HEADER: license_key},
            timeout=3,
        )
    except Exception:
        pass
