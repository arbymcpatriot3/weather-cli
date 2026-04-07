#!/usr/bin/env python3
# tests/test_alerts.py — Clean Shot: alert engine tests

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.alerts import (
    get_road_alerts, diesel_gel_risk,
    has_critical, filter_by_severity,
    _check_black_ice, _check_bridge_freeze, _check_fog,
    _check_flood, _check_diesel_gel, _check_high_wind, _check_mudslide,
)


# ── Helper to build minimal parsed dicts ─────────────────────────────────────

def _current(temp=50, code=0, wind_speed=10, wind_gust=12, humidity=50):
    return {"temp": temp, "code": code, "wind_speed": wind_speed,
            "wind_gust": wind_gust, "humidity": humidity, "feels": temp - 3}

def _hourly(temps=None, precip_probs=None, wind_gusts=None):
    temps       = temps       or [50]*24
    precip_probs = precip_probs or [0]*24
    wind_gusts  = wind_gusts  or [0]*24
    return {"temps": temps, "precip_probs": precip_probs, "wind_gusts": wind_gusts}

def _forecast(rain_prob=10, high=60, low=40):
    return [{"rain_prob": rain_prob, "high": high, "low": low,
             "gust_max": 15, "wind_max": 10}]

def _parsed(temp=50, code=0, wind_speed=10, wind_gust=12,
            precip_probs=None, hourly_temps=None, hourly_gusts=None,
            rain_prob=10):
    return {
        "current":  _current(temp, code, wind_speed, wind_gust),
        "hourly":   _hourly(hourly_temps, precip_probs, hourly_gusts),
        "forecast": _forecast(rain_prob),
    }


# ── diesel_gel_risk ───────────────────────────────────────────────────────────

def test_diesel_gel_risk():
    assert diesel_gel_risk(25)  == "none"
    assert diesel_gel_risk(18)  == "watch"
    assert diesel_gel_risk(10)  == "warning"
    assert diesel_gel_risk(-5)  == "emergency"
    # boundary checks
    assert diesel_gel_risk(20)  == "watch"   # exactly at watch threshold
    assert diesel_gel_risk(15)  == "warning" # exactly at warning threshold
    assert diesel_gel_risk(0)   == "emergency"
    print("✓ diesel_gel_risk")


# ── Black ice ─────────────────────────────────────────────────────────────────

def test_black_ice_triggers_in_range_with_precip():
    cur    = _current(temp=31, code=61)   # rain at 31°F — WARNING (CRITICAL is ≤ 30°F)
    hourly = _hourly(precip_probs=[50]*24)
    a = _check_black_ice(cur, hourly)
    assert a is not None
    assert a["type"]     == "black_ice"
    assert a["severity"] == "WARNING"
    print("✓ black_ice: triggers WARNING at 31°F + rain")


def test_black_ice_critical_at_29():
    cur    = _current(temp=29, code=61)   # rain at 29°F — CRITICAL
    hourly = _hourly(precip_probs=[50]*24)
    a = _check_black_ice(cur, hourly)
    assert a is not None
    assert a["severity"] == "CRITICAL"
    print("✓ black_ice: CRITICAL at 29°F + rain")


def test_black_ice_warning_at_33():
    cur    = _current(temp=33, code=0)
    hourly = _hourly(precip_probs=[30]*24)
    a = _check_black_ice(cur, hourly)
    assert a is not None
    assert a["severity"] == "WARNING"
    print("✓ black_ice: WARNING at 33°F + precip prob")


def test_black_ice_no_precip_no_trigger():
    cur    = _current(temp=31, code=0)
    hourly = _hourly(precip_probs=[5]*24)  # very low probability
    a = _check_black_ice(cur, hourly)
    assert a is None
    print("✓ black_ice: no trigger without precip")


def test_black_ice_too_warm():
    cur    = _current(temp=45, code=61)
    hourly = _hourly(precip_probs=[80]*24)
    assert _check_black_ice(cur, hourly) is None
    print("✓ black_ice: no trigger above 34°F")


def test_black_ice_too_cold():
    cur    = _current(temp=10, code=71)   # heavy snow at 10°F
    hourly = _hourly(precip_probs=[80]*24)
    assert _check_black_ice(cur, hourly) is None
    print("✓ black_ice: no trigger below 20°F (hard ice, not black ice)")


# ── Bridge freeze ─────────────────────────────────────────────────────────────

def test_bridge_freeze_critical():
    a = _check_bridge_freeze(_current(temp=28))
    assert a is not None
    assert a["type"]     == "bridge_freeze"
    assert a["severity"] == "CRITICAL"
    print("✓ bridge_freeze: CRITICAL at 28°F")


def test_bridge_freeze_warning():
    a = _check_bridge_freeze(_current(temp=35))
    assert a is not None
    assert a["severity"] == "WARNING"
    print("✓ bridge_freeze: WARNING at 35°F")


def test_bridge_freeze_no_trigger():
    assert _check_bridge_freeze(_current(temp=40)) is None
    print("✓ bridge_freeze: no trigger at 40°F")


# ── Fog ───────────────────────────────────────────────────────────────────────

def test_fog_warning():
    a = _check_fog(_current(code=45), _hourly())
    assert a is not None
    assert a["type"]     == "fog"
    assert a["severity"] == "WARNING"
    print("✓ fog: WARNING for code 45")


def test_icy_fog_critical():
    a = _check_fog(_current(code=48), _hourly())
    assert a is not None
    assert a["severity"] == "CRITICAL"
    print("✓ fog: CRITICAL for code 48 (icy fog)")


def test_fog_no_trigger():
    assert _check_fog(_current(code=3), _hourly()) is None
    print("✓ fog: no trigger for overcast (code 3)")


# ── Flood ─────────────────────────────────────────────────────────────────────

def test_flood_critical():
    cur    = _current(code=65)   # heavy rain
    hourly = _hourly(precip_probs=[90]*24)
    fc     = _forecast(rain_prob=90)
    a = _check_flood(cur, hourly, fc)
    assert a is not None
    assert a["type"]     == "flood"
    assert a["severity"] == "CRITICAL"
    print("✓ flood: CRITICAL with heavy rain + 90% precip")


def test_flood_warning():
    cur    = _current(code=0)
    hourly = _hourly(precip_probs=[80]*24)
    fc     = _forecast(rain_prob=70)
    a = _check_flood(cur, hourly, fc)
    assert a is not None
    assert a["severity"] in ("WARNING", "CRITICAL")
    print("✓ flood: triggers with sustained 80% precip probability")


def test_flood_no_trigger():
    cur    = _current(code=1)
    hourly = _hourly(precip_probs=[20]*24)
    fc     = _forecast(rain_prob=25)
    assert _check_flood(cur, hourly, fc) is None
    print("✓ flood: no trigger with low precip probability")


# ── Diesel gel ────────────────────────────────────────────────────────────────

def test_diesel_gel_critical():
    cur    = _current(temp=-5)
    hourly = _hourly(temps=[-5]*24)
    a = _check_diesel_gel(cur, hourly)
    assert a is not None
    assert a["type"]     == "diesel_gel"
    assert a["severity"] == "CRITICAL"
    print("✓ diesel_gel: CRITICAL at -5°F")


def test_diesel_gel_warning():
    cur    = _current(temp=12)
    hourly = _hourly(temps=[10]*24)
    a = _check_diesel_gel(cur, hourly)
    assert a is not None
    assert a["severity"] == "WARNING"
    print("✓ diesel_gel: WARNING at 12°F")


def test_diesel_gel_watch():
    cur    = _current(temp=18)
    hourly = _hourly(temps=[16]*24)
    a = _check_diesel_gel(cur, hourly)
    assert a is not None
    assert a["severity"] == "INFO"
    print("✓ diesel_gel: INFO/watch at 18°F")


def test_diesel_gel_no_trigger():
    cur    = _current(temp=40)
    hourly = _hourly(temps=[35]*24)
    assert _check_diesel_gel(cur, hourly) is None
    print("✓ diesel_gel: no trigger above 20°F")


def test_diesel_gel_uses_coldest_upcoming():
    # Current temp is fine but it's about to get cold
    cur    = _current(temp=25)
    hourly = _hourly(temps=[25, 22, 18, 12, 8, 5] + [5]*18)
    a = _check_diesel_gel(cur, hourly)
    assert a is not None
    assert a["severity"] in ("WARNING", "CRITICAL")
    print("✓ diesel_gel: uses coldest upcoming temp (not just current)")


# ── High wind ─────────────────────────────────────────────────────────────────

def test_high_wind_critical():
    cur    = _current(wind_speed=55, wind_gust=65)
    hourly = _hourly(wind_gusts=[65]*24)
    cfg    = {"vehicle_type": "semi", "wind_alert_mph": 40}
    a = _check_high_wind(cur, hourly, cfg)
    assert a is not None
    assert a["type"]     == "high_wind"
    assert a["severity"] == "CRITICAL"
    print("✓ high_wind: CRITICAL at 65 mph gusts (threshold 40)")


def test_high_wind_warning():
    cur    = _current(wind_speed=35, wind_gust=42)
    hourly = _hourly(wind_gusts=[42]*24)
    cfg    = {"vehicle_type": "semi", "wind_alert_mph": 40}
    a = _check_high_wind(cur, hourly, cfg)
    assert a is not None
    assert a["severity"] == "WARNING"
    print("✓ high_wind: WARNING at 42 mph gusts")


def test_high_wind_tanker_lower_threshold():
    # Tanker factor is 0.85 — triggers at lower wind speed
    cur    = _current(wind_speed=30, wind_gust=35)
    hourly = _hourly(wind_gusts=[35]*24)
    cfg    = {"vehicle_type": "tanker", "wind_alert_mph": 40}
    # threshold = 40 * 0.85 = 34 mph — 35 mph gust should trigger
    a = _check_high_wind(cur, hourly, cfg)
    assert a is not None
    print("✓ high_wind: tanker triggers at lower threshold than semi")


def test_high_wind_no_trigger():
    cur    = _current(wind_speed=10, wind_gust=15)
    hourly = _hourly(wind_gusts=[15]*24)
    cfg    = {"vehicle_type": "semi", "wind_alert_mph": 40}
    assert _check_high_wind(cur, hourly, cfg) is None
    print("✓ high_wind: no trigger at 15 mph gusts")


def test_high_wind_uses_12h_forecast():
    # Current gust is fine but upcoming is severe
    cur    = _current(wind_speed=20, wind_gust=22)
    gusts  = [22]*3 + [55]*9 + [20]*12
    hourly = _hourly(wind_gusts=gusts)
    cfg    = {"vehicle_type": "semi", "wind_alert_mph": 40}
    a = _check_high_wind(cur, hourly, cfg)
    assert a is not None
    assert a["severity"] in ("WARNING", "CRITICAL")
    print("✓ high_wind: triggers on upcoming gusts, not just current")


# ── Mudslide ──────────────────────────────────────────────────────────────────

def test_mudslide_warning():
    cur    = _current(code=65)   # heavy rain
    hourly = _hourly(precip_probs=[85]*24)
    fc     = _forecast(rain_prob=85)
    a = _check_mudslide(cur, hourly, fc)
    assert a is not None
    assert a["type"] == "mudslide"
    print("✓ mudslide: triggers with heavy rain + high probability")


def test_mudslide_no_trigger_light_rain():
    cur    = _current(code=51)   # light drizzle
    hourly = _hourly(precip_probs=[40]*24)
    fc     = _forecast(rain_prob=40)
    assert _check_mudslide(cur, hourly, fc) is None
    print("✓ mudslide: no trigger with light rain")


# ── Master function ───────────────────────────────────────────────────────────

def test_get_road_alerts_returns_list():
    result = get_road_alerts(35.15, -90.05, {})
    assert isinstance(result, list)
    print("✓ get_road_alerts: returns list on empty parsed")


def test_get_road_alerts_sorted_by_severity():
    # Setup conditions that trigger multiple alerts at different severities
    parsed = _parsed(
        temp=31, code=61,               # black ice (CRITICAL)
        precip_probs=[90]*24,           # flood risk
        hourly_gusts=[45]*24,           # wind warning
        rain_prob=90,
    )
    cfg    = {"vehicle_type": "semi", "wind_alert_mph": 40}
    alerts = get_road_alerts(0, 0, parsed, cfg)
    assert isinstance(alerts, list)
    # Verify CRITICAL comes before WARNING comes before INFO
    severities = [a["severity"] for a in alerts]
    order      = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    assert severities == sorted(severities, key=lambda s: order.get(s, 9))
    print(f"✓ get_road_alerts: sorted correctly — {severities}")


def test_has_critical():
    alerts = [{"severity": "WARNING"}, {"severity": "CRITICAL"}]
    assert has_critical(alerts) is True
    assert has_critical([{"severity": "WARNING"}]) is False
    print("✓ has_critical")


def test_filter_by_severity():
    alerts = [
        {"severity": "CRITICAL", "type": "a"},
        {"severity": "WARNING",  "type": "b"},
        {"severity": "INFO",     "type": "c"},
        {"severity": "CRITICAL", "type": "d"},
    ]
    crits = filter_by_severity(alerts, "CRITICAL")
    assert len(crits) == 2
    assert all(a["severity"] == "CRITICAL" for a in crits)
    print("✓ filter_by_severity")


def test_all_alerts_have_cb_voice():
    # Every alert that fires must have a non-empty cb_voice string
    conditions = [
        _parsed(temp=31, code=61, precip_probs=[50]*24),        # black ice
        _parsed(temp=30),                                         # bridge freeze
        _parsed(code=45),                                         # fog
        _parsed(temp=10, code=65, precip_probs=[90]*24, rain_prob=90),  # flood + gel
        _parsed(hourly_gusts=[65]*24),                            # wind
    ]
    cfg = {"vehicle_type": "semi", "wind_alert_mph": 40}
    for p in conditions:
        for a in get_road_alerts(0, 0, p, cfg):
            assert a.get("cb_voice"), f"Missing cb_voice for {a['type']}"
    print("✓ all triggered alerts have cb_voice strings")


# ── Run all ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n── diesel_gel_risk ──")
    test_diesel_gel_risk()

    print("\n── black_ice ──")
    test_black_ice_triggers_in_range_with_precip()
    test_black_ice_critical_at_29()
    test_black_ice_warning_at_33()
    test_black_ice_no_precip_no_trigger()
    test_black_ice_too_warm()
    test_black_ice_too_cold()

    print("\n── bridge_freeze ──")
    test_bridge_freeze_critical()
    test_bridge_freeze_warning()
    test_bridge_freeze_no_trigger()

    print("\n── fog ──")
    test_fog_warning()
    test_icy_fog_critical()
    test_fog_no_trigger()

    print("\n── flood ──")
    test_flood_critical()
    test_flood_warning()
    test_flood_no_trigger()

    print("\n── diesel_gel ──")
    test_diesel_gel_critical()
    test_diesel_gel_warning()
    test_diesel_gel_watch()
    test_diesel_gel_no_trigger()
    test_diesel_gel_uses_coldest_upcoming()

    print("\n── high_wind ──")
    test_high_wind_critical()
    test_high_wind_warning()
    test_high_wind_tanker_lower_threshold()
    test_high_wind_no_trigger()
    test_high_wind_uses_12h_forecast()

    print("\n── mudslide ──")
    test_mudslide_warning()
    test_mudslide_no_trigger_light_rain()

    print("\n── master function ──")
    test_get_road_alerts_returns_list()
    test_get_road_alerts_sorted_by_severity()
    test_has_critical()
    test_filter_by_severity()
    test_all_alerts_have_cb_voice()

    print("\n✅  All alert tests passed.")
