#!/usr/bin/env python3
# tests/test_alerts.py — Clean Shot: alert engine tests
# TODO: implement tests alongside core/alerts.py

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.alerts import diesel_gel_risk, get_road_alerts


def test_diesel_gel_risk():
    assert diesel_gel_risk(25)  == "none"
    assert diesel_gel_risk(18)  == "watch"
    assert diesel_gel_risk(10)  == "warning"
    assert diesel_gel_risk(-5)  == "emergency"
    print("✓ diesel_gel_risk")


def test_get_road_alerts_returns_list():
    # Stub returns empty list — test that the contract holds
    result = get_road_alerts(35.15, -90.05, {})
    assert isinstance(result, list)
    print("✓ get_road_alerts returns list")


if __name__ == "__main__":
    test_diesel_gel_risk()
    test_get_road_alerts_returns_list()
    print("All alert tests passed.")
