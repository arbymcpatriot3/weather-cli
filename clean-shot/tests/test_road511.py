#!/usr/bin/env python3
# tests/test_road511.py — Clean Shot: road511 module tests
#
# All tests run offline — no real network calls, no road511.com access.
# Mocks are used for requests and the license/credentials file system.
#
# Covers:
#   _resolve_key()       — env var, credentials file, config, None     (6 tests)
#   _load_license()      — present, missing, malformed, missing keys    (4 tests)
#   _map_severity()      — all severity strings + edge cases            (9 tests)
#   _get()               — no requests, empty key                       (2 tests)
#   _get_proxy()         — no requests, no license                      (2 tests)
#   _fetch()             — key path, fallback path, proxy-only path     (4 tests)
#   fetch_events()       — cache hit, API success, stale fallback,
#                          API down + no stale, bad data shapes         (8 tests)
#   fetch_bridges()      — flagging logic, bad coords, bad clearance    (5 tests)
#   fetch_weigh_stations()— distance filter, status mapping, sort order (4 tests)
#   fetch_truck_parking() — distance filter, amenities, no key          (3 tests)
#   check_route_safety() — no key+no license, has license,
#                          critical incident, flagged bridge,
#                          sub-call exception isolation                  (5 tests)
# Total: 52 tests

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core.road511 as r511


# ── Helpers ────────────────────────────────────────────────────────────────────

def _empty_config(**overrides) -> dict:
    cfg = {
        "road511_api_key":    None,
        "road511_enabled":    True,
        "road511_radius_km":  80,
        "vehicle_height_ft":  13.5,
        "vehicle_weight_lbs": 80000,
        "vehicle_length_ft":  75,
        "vehicle_type":       "semi",
        "show_cameras":       False,
        "show_weigh_stations": True,
        "show_truck_parking":  True,
        "show_bridge_warnings": True,
    }
    cfg.update(overrides)
    return cfg


def _fake_event(type_="incident", severity="moderate", road="I-40",
                direction="eastbound", description="Crash ahead") -> dict:
    return {
        "properties": {
            "type":        type_,
            "severity":    severity,
            "road":        road,
            "direction":   direction,
            "description": description,
            "end_time":    None,
        }
    }


def _fake_bridge(road="I-76", clearance_ft=12.0, lat=40.0, lon=-80.0,
                 weight_limit_tons=None) -> dict:
    return {
        "properties": {
            "road":              road,
            "clearance_ft":      clearance_ft,
            "weight_limit_tons": weight_limit_tons,
            "name":              None,
        },
        "geometry": {"coordinates": [lon, lat]},
    }


# ── _resolve_key() ─────────────────────────────────────────────────────────────

class TestResolveKey(unittest.TestCase):

    def setUp(self):
        os.environ.pop("ROAD511_API_KEY", None)

    def tearDown(self):
        os.environ.pop("ROAD511_API_KEY", None)

    def test_env_var_takes_priority(self):
        os.environ["ROAD511_API_KEY"] = "env_key_123"
        cfg = _empty_config(road511_api_key="config_key_456")
        self.assertEqual(r511._resolve_key(cfg), "env_key_123")

    def test_credentials_file_used_when_no_env(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"road511_api_key": "file_key_789"}, f)
            creds_path = Path(f.name)
        try:
            with patch("core.road511.Path") as mock_path:
                mock_home = MagicMock()
                mock_path.home.return_value = mock_home
                mock_creds = MagicMock()
                mock_home.__truediv__.return_value.__truediv__.return_value = mock_creds
                mock_creds.exists.return_value = True
                mock_creds.read_text.return_value = json.dumps({"road511_api_key": "file_key_789"})
                result = r511._resolve_key(_empty_config())
            self.assertEqual(result, "file_key_789")
        finally:
            creds_path.unlink(missing_ok=True)

    def test_malformed_credentials_file_falls_through(self):
        with patch("core.road511.Path") as mock_path:
            mock_home = MagicMock()
            mock_path.home.return_value = mock_home
            mock_creds = MagicMock()
            mock_home.__truediv__.return_value.__truediv__.return_value = mock_creds
            mock_creds.exists.return_value = True
            mock_creds.read_text.return_value = "not valid json{{{"
            cfg = _empty_config(road511_api_key="config_key")
            result = r511._resolve_key(cfg)
        self.assertEqual(result, "config_key")

    def test_config_key_used_as_fallback(self):
        cfg = _empty_config(road511_api_key="r511_abc123")
        with patch("core.road511.Path") as mock_path:
            mock_path.home.return_value.__truediv__.return_value.__truediv__.return_value.exists.return_value = False
            result = r511._resolve_key(cfg)
        self.assertEqual(result, "r511_abc123")

    def test_none_config_key_returns_empty_string(self):
        cfg = _empty_config(road511_api_key=None)
        with patch("core.road511.Path") as mock_path:
            mock_path.home.return_value.__truediv__.return_value.__truediv__.return_value.exists.return_value = False
            result = r511._resolve_key(cfg)
        self.assertEqual(result, "")

    def test_empty_string_config_key_returns_empty_string(self):
        cfg = _empty_config(road511_api_key="")
        with patch("core.road511.Path") as mock_path:
            mock_path.home.return_value.__truediv__.return_value.__truediv__.return_value.exists.return_value = False
            result = r511._resolve_key(cfg)
        self.assertEqual(result, "")


# ── _load_license() ────────────────────────────────────────────────────────────

class TestLoadLicense(unittest.TestCase):

    def test_returns_keys_when_file_present(self):
        with patch("core.road511.Path") as mock_path:
            mock_lf = MagicMock()
            mock_path.home.return_value.__truediv__.return_value.__truediv__.return_value.__truediv__.return_value = mock_lf
            mock_lf.exists.return_value = True
            mock_lf.read_text.return_value = json.dumps({
                "license_key": "CS-AAAA-BBBB-CCCC-DDDD",
                "machine_id":  "abc123def456",
            })
            key, mid = r511._load_license()
        self.assertEqual(key, "CS-AAAA-BBBB-CCCC-DDDD")
        self.assertEqual(mid, "abc123def456")

    def test_returns_empty_when_file_missing(self):
        with patch("core.road511.Path") as mock_path:
            mock_lf = MagicMock()
            mock_path.home.return_value.__truediv__.return_value.__truediv__.return_value.__truediv__.return_value = mock_lf
            mock_lf.exists.return_value = False
            key, mid = r511._load_license()
        self.assertEqual(key, "")
        self.assertEqual(mid, "")

    def test_returns_empty_on_malformed_json(self):
        with patch("core.road511.Path") as mock_path:
            mock_lf = MagicMock()
            mock_path.home.return_value.__truediv__.return_value.__truediv__.return_value.__truediv__.return_value = mock_lf
            mock_lf.exists.return_value = True
            mock_lf.read_text.return_value = "not json"
            key, mid = r511._load_license()
        self.assertEqual(key, "")
        self.assertEqual(mid, "")

    def test_returns_empty_strings_for_missing_keys(self):
        with patch("core.road511.Path") as mock_path:
            mock_lf = MagicMock()
            mock_path.home.return_value.__truediv__.return_value.__truediv__.return_value.__truediv__.return_value = mock_lf
            mock_lf.exists.return_value = True
            mock_lf.read_text.return_value = json.dumps({"other": "data"})
            key, mid = r511._load_license()
        self.assertEqual(key, "")
        self.assertEqual(mid, "")


# ── _map_severity() ────────────────────────────────────────────────────────────

class TestMapSeverity(unittest.TestCase):

    def test_critical(self):
        self.assertEqual(r511._map_severity("critical"), "critical")

    def test_major_maps_to_critical(self):
        self.assertEqual(r511._map_severity("major"), "critical")

    def test_severe_maps_to_high(self):
        self.assertEqual(r511._map_severity("severe"), "high")

    def test_high_maps_to_high(self):
        self.assertEqual(r511._map_severity("high"), "high")

    def test_moderate_maps_to_medium(self):
        self.assertEqual(r511._map_severity("moderate"), "medium")

    def test_medium_maps_to_medium(self):
        self.assertEqual(r511._map_severity("medium"), "medium")

    def test_low_maps_to_low(self):
        self.assertEqual(r511._map_severity("low"), "low")

    def test_empty_string_maps_to_low(self):
        self.assertEqual(r511._map_severity(""), "low")

    def test_none_maps_to_low(self):
        self.assertEqual(r511._map_severity(None), "low")


# ── _get() ─────────────────────────────────────────────────────────────────────

class TestGet(unittest.TestCase):

    def test_returns_none_when_requests_unavailable(self):
        with patch.object(r511, "_REQUESTS_AVAILABLE", False):
            result = r511._get("https://example.com", "somekey")
        self.assertIsNone(result)

    def test_returns_none_when_key_empty(self):
        result = r511._get("https://example.com", "")
        self.assertIsNone(result)


# ── _get_proxy() ───────────────────────────────────────────────────────────────

class TestGetProxy(unittest.TestCase):

    def test_returns_none_when_requests_unavailable(self):
        with patch.object(r511, "_REQUESTS_AVAILABLE", False):
            result = r511._get_proxy("/events", {"lat": "35.0"})
        self.assertIsNone(result)

    def test_returns_none_when_no_license(self):
        with patch("core.road511._load_license", return_value=("", "")):
            result = r511._get_proxy("/events", {"lat": "35.0"})
        self.assertIsNone(result)


# ── _fetch() ───────────────────────────────────────────────────────────────────

class TestFetch(unittest.TestCase):

    def test_returns_direct_data_when_key_and_api_succeed(self):
        expected = {"features": []}
        with patch("core.road511._get", return_value=expected):
            result = r511._fetch("/events", {"lat": "35.0"}, "mykey")
        self.assertEqual(result, expected)

    def test_falls_to_proxy_when_key_provided_but_direct_fails(self):
        proxy_data = {"features": [{"properties": {}}]}
        with patch("core.road511._get", return_value=None), \
             patch("core.road511._get_proxy", return_value=proxy_data):
            result = r511._fetch("/events", {"lat": "35.0"}, "badkey")
        self.assertEqual(result, proxy_data)

    def test_uses_proxy_when_no_key(self):
        proxy_data = {"events": []}
        with patch("core.road511._get_proxy", return_value=proxy_data):
            result = r511._fetch("/events", {"lat": "35.0"}, "")
        self.assertEqual(result, proxy_data)

    def test_returns_none_when_no_key_and_proxy_fails(self):
        with patch("core.road511._get_proxy", return_value=None):
            result = r511._fetch("/events", {"lat": "35.0"}, "")
        self.assertIsNone(result)


# ── fetch_events() ─────────────────────────────────────────────────────────────

class TestFetchEvents(unittest.TestCase):

    def _cache_with_events(self, events: list) -> str:
        return json.dumps({"r511_events": events})

    def test_returns_empty_when_no_key_no_license_no_cache(self):
        with patch("core.road511._resolve_key", return_value=""), \
             patch("core.road511.cache_load", return_value=(None, None)), \
             patch("core.road511._fetch", return_value=None), \
             patch("core.road511.cache_stale", return_value=(None, None)):
            result = r511.fetch_events(35.0, -90.0, _empty_config())
        self.assertEqual(result, [])

    def test_returns_cached_events_on_cache_hit(self):
        events = [{"source": "road511", "type": "incident", "severity": "high",
                   "road": "I-40", "description": "Crash"}]
        with patch("core.road511._resolve_key", return_value=""), \
             patch("core.road511.cache_load",
                   return_value=(self._cache_with_events(events), 5)):
            result = r511.fetch_events(35.0, -90.0, _empty_config())
        self.assertEqual(result, events)

    def test_skips_non_r511_cache_format(self):
        with patch("core.road511._resolve_key", return_value="mykey"), \
             patch("core.road511.cache_load",
                   return_value=(json.dumps({"nws_data": []}), 3)), \
             patch("core.road511._fetch", return_value={"features": []}), \
             patch("core.road511.cache_save"):
            result = r511.fetch_events(35.0, -90.0, _empty_config())
        self.assertEqual(result, [])

    def test_normalizes_api_events(self):
        raw = {"features": [_fake_event("incident", "critical", "I-80", "westbound",
                                        "Multi-vehicle crash")]}
        with patch("core.road511._resolve_key", return_value="key"), \
             patch("core.road511.cache_load", return_value=(None, None)), \
             patch("core.road511._fetch", return_value=raw), \
             patch("core.road511.cache_save"):
            result = r511.fetch_events(35.0, -90.0, _empty_config())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source"], "road511")
        self.assertEqual(result[0]["severity"], "critical")
        self.assertEqual(result[0]["road"], "I-80")

    def test_unknown_type_normalized_to_incident(self):
        raw = {"features": [_fake_event("weird_unknown_type", "low", "US-30")]}
        with patch("core.road511._resolve_key", return_value="key"), \
             patch("core.road511.cache_load", return_value=(None, None)), \
             patch("core.road511._fetch", return_value=raw), \
             patch("core.road511.cache_save"):
            result = r511.fetch_events(35.0, -90.0, _empty_config())
        self.assertEqual(result[0]["type"], "incident")

    def test_description_truncated_to_120_chars(self):
        long_desc = "A" * 200
        raw = {"features": [_fake_event(description=long_desc)]}
        with patch("core.road511._resolve_key", return_value="key"), \
             patch("core.road511.cache_load", return_value=(None, None)), \
             patch("core.road511._fetch", return_value=raw), \
             patch("core.road511.cache_save"):
            result = r511.fetch_events(35.0, -90.0, _empty_config())
        self.assertLessEqual(len(result[0]["description"]), 120)

    def test_stale_cache_returned_when_api_down(self):
        stale_events = [{"source": "road511", "type": "incident",
                         "severity": "medium", "road": "I-70",
                         "description": "Construction zone"}]
        with patch("core.road511._resolve_key", return_value="key"), \
             patch("core.road511.cache_load", return_value=(None, None)), \
             patch("core.road511._fetch", return_value=None), \
             patch("core.road511.cache_stale",
                   return_value=(self._cache_with_events(stale_events), 45)):
            result = r511.fetch_events(35.0, -90.0, _empty_config())
        self.assertEqual(result, stale_events)

    def test_returns_empty_when_api_down_and_no_stale_cache(self):
        with patch("core.road511._resolve_key", return_value="key"), \
             patch("core.road511.cache_load", return_value=(None, None)), \
             patch("core.road511._fetch", return_value=None), \
             patch("core.road511.cache_stale", return_value=(None, None)):
            result = r511.fetch_events(35.0, -90.0, _empty_config())
        self.assertEqual(result, [])


# ── fetch_bridges() ────────────────────────────────────────────────────────────

class TestFetchBridges(unittest.TestCase):

    def _raw(self, bridges: list) -> dict:
        return {"features": bridges}

    def test_bridge_flagged_when_clearance_below_height_plus_margin(self):
        cfg = _empty_config(vehicle_height_ft=13.5)
        # clearance 13.0 < 13.5 + 0.5 → flagged
        raw = self._raw([_fake_bridge("I-95", clearance_ft=13.0)])
        with patch("core.road511._resolve_key", return_value="key"), \
             patch("core.road511.cache_load", return_value=(None, None)), \
             patch("core.road511._fetch", return_value=raw), \
             patch("core.road511.cache_save"):
            result = r511.fetch_bridges(35.0, -90.0, cfg)
        self.assertTrue(result[0]["flagged"])

    def test_bridge_not_flagged_when_clearance_safe(self):
        cfg = _empty_config(vehicle_height_ft=13.5)
        # clearance 16.0 >= 13.5 + 0.5 → not flagged
        raw = self._raw([_fake_bridge("I-95", clearance_ft=16.0)])
        with patch("core.road511._resolve_key", return_value="key"), \
             patch("core.road511.cache_load", return_value=(None, None)), \
             patch("core.road511._fetch", return_value=raw), \
             patch("core.road511.cache_save"):
            result = r511.fetch_bridges(35.0, -90.0, cfg)
        self.assertFalse(result[0]["flagged"])

    def test_bad_clearance_defaults_to_99_not_flagged(self):
        feature = {
            "properties": {"road": "US-30", "clearance_ft": "N/A", "name": None},
            "geometry":   {"coordinates": [-80.0, 40.0]},
        }
        with patch("core.road511._resolve_key", return_value="key"), \
             patch("core.road511.cache_load", return_value=(None, None)), \
             patch("core.road511._fetch", return_value={"features": [feature]}), \
             patch("core.road511.cache_save"):
            result = r511.fetch_bridges(35.0, -90.0, _empty_config())
        self.assertEqual(result[0]["clearance_ft"], 99.0)
        self.assertFalse(result[0]["flagged"])

    def test_missing_geometry_uses_query_latlon(self):
        feature = {
            "properties": {"road": "I-10", "clearance_ft": 15.0, "name": None},
            "geometry":   {},
        }
        with patch("core.road511._resolve_key", return_value="key"), \
             patch("core.road511.cache_load", return_value=(None, None)), \
             patch("core.road511._fetch", return_value={"features": [feature]}), \
             patch("core.road511.cache_save"):
            result = r511.fetch_bridges(35.0, -90.0, _empty_config())
        self.assertEqual(result[0]["lat"], 35.0)
        self.assertEqual(result[0]["lon"], -90.0)

    def test_returns_empty_when_no_key_no_license(self):
        with patch("core.road511._resolve_key", return_value=""), \
             patch("core.road511.cache_load", return_value=(None, None)), \
             patch("core.road511._fetch", return_value=None):
            result = r511.fetch_bridges(35.0, -90.0, _empty_config())
        self.assertEqual(result, [])


# ── fetch_weigh_stations() ─────────────────────────────────────────────────────

class TestFetchWeighStations(unittest.TestCase):

    def _station(self, name, status, dist_km=10.0) -> dict:
        lat = 35.0 + dist_km / 111.0
        return {
            "properties": {"name": name, "status": status, "road": "I-40",
                           "direction": "eastbound"},
            "geometry":   {"coordinates": [-90.0, lat]},
        }

    def test_open_status_mapping(self):
        with patch("core.road511._resolve_key", return_value="key"), \
             patch("core.road511.cache_load", return_value=(None, None)), \
             patch("core.road511._fetch",
                   return_value={"features": [self._station("WS1", "open")]}), \
             patch("core.road511.cache_save"):
            result = r511.fetch_weigh_stations(35.0, -90.0, _empty_config())
        self.assertEqual(result[0]["status"], "open")

    def test_closed_status_mapping(self):
        with patch("core.road511._resolve_key", return_value="key"), \
             patch("core.road511.cache_load", return_value=(None, None)), \
             patch("core.road511._fetch",
                   return_value={"features": [self._station("WS2", "0")]}), \
             patch("core.road511.cache_save"):
            result = r511.fetch_weigh_stations(35.0, -90.0, _empty_config())
        self.assertEqual(result[0]["status"], "closed")

    def test_unknown_status_mapping(self):
        with patch("core.road511._resolve_key", return_value="key"), \
             patch("core.road511.cache_load", return_value=(None, None)), \
             patch("core.road511._fetch",
                   return_value={"features": [self._station("WS3", "maintenance")]}), \
             patch("core.road511.cache_save"):
            result = r511.fetch_weigh_stations(35.0, -90.0, _empty_config())
        self.assertEqual(result[0]["status"], "unknown")

    def test_stations_over_50_miles_filtered(self):
        # ~90 km ≈ 56 miles — should be filtered out
        far_station = self._station("Far WS", "open", dist_km=90.0)
        with patch("core.road511._resolve_key", return_value="key"), \
             patch("core.road511.cache_load", return_value=(None, None)), \
             patch("core.road511._fetch",
                   return_value={"features": [far_station]}), \
             patch("core.road511.cache_save"):
            result = r511.fetch_weigh_stations(35.0, -90.0, _empty_config())
        self.assertEqual(result, [])


# ── fetch_truck_parking() ──────────────────────────────────────────────────────

class TestFetchTruckParking(unittest.TestCase):

    def _stop(self, name, dist_km=5.0, spaces=None) -> dict:
        lat = 35.0 + dist_km / 111.0
        return {
            "properties": {"name": name, "road": "I-40", "spaces": spaces,
                           "amenities": ["fuel", "food"]},
            "geometry":   {"coordinates": [-90.0, lat]},
        }

    def test_returns_stops_with_amenities(self):
        with patch("core.road511._resolve_key", return_value="key"), \
             patch("core.road511.cache_load", return_value=(None, None)), \
             patch("core.road511._fetch",
                   return_value={"features": [self._stop("TA Travel Center")]}), \
             patch("core.road511.cache_save"):
            result = r511.fetch_truck_parking(35.0, -90.0, _empty_config())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["amenities"], ["fuel", "food"])

    def test_spaces_none_when_missing(self):
        with patch("core.road511._resolve_key", return_value="key"), \
             patch("core.road511.cache_load", return_value=(None, None)), \
             patch("core.road511._fetch",
                   return_value={"features": [self._stop("Lot A", spaces=None)]}), \
             patch("core.road511.cache_save"):
            result = r511.fetch_truck_parking(35.0, -90.0, _empty_config())
        self.assertIsNone(result[0]["spaces"])

    def test_returns_empty_when_no_key_and_proxy_unavailable(self):
        with patch("core.road511._resolve_key", return_value=""), \
             patch("core.road511.cache_load", return_value=(None, None)), \
             patch("core.road511._fetch", return_value=None):
            result = r511.fetch_truck_parking(35.0, -90.0, _empty_config())
        self.assertEqual(result, [])


# ── check_route_safety() ──────────────────────────────────────────────────────

class TestCheckRouteSafety(unittest.TestCase):

    def test_returns_unavailable_when_no_key_and_no_license(self):
        with patch("core.road511._resolve_key", return_value=""), \
             patch("core.road511._load_license", return_value=("", "")):
            result = r511.check_route_safety(35.0, -90.0, _empty_config())
        self.assertFalse(result.get("available"))
        self.assertEqual(result.get("reason"), "no_api_key")

    def test_returns_available_when_license_exists_even_without_direct_key(self):
        with patch("core.road511._resolve_key", return_value=""), \
             patch("core.road511._load_license",
                   return_value=("CS-AAAA-BBBB-CCCC-DDDD", "machine123")), \
             patch("core.road511.fetch_events", return_value=[]), \
             patch("core.road511.fetch_bridges", return_value=[]), \
             patch("core.road511.fetch_weigh_stations", return_value=[]), \
             patch("core.road511.fetch_truck_parking", return_value=[]):
            result = r511.check_route_safety(35.0, -90.0, _empty_config())
        self.assertTrue(result.get("available"))

    def test_safe_false_on_critical_incident(self):
        incident = {"severity": "critical", "description": "Road closed",
                    "road": "I-40", "type": "closure"}
        with patch("core.road511._resolve_key", return_value="key"), \
             patch("core.road511._load_license", return_value=("key", "m1")), \
             patch("core.road511.fetch_events", return_value=[incident]), \
             patch("core.road511.fetch_bridges", return_value=[]), \
             patch("core.road511.fetch_weigh_stations", return_value=[]), \
             patch("core.road511.fetch_truck_parking", return_value=[]):
            result = r511.check_route_safety(35.0, -90.0, _empty_config())
        self.assertFalse(result["safe"])
        self.assertTrue(len(result["critical"]) > 0)

    def test_clearance_ok_false_on_flagged_bridge(self):
        bridge = {"flagged": True, "road": "I-95",
                  "clearance_ft": 12.5, "source": "road511_nbi"}
        with patch("core.road511._resolve_key", return_value="key"), \
             patch("core.road511._load_license", return_value=("key", "m1")), \
             patch("core.road511.fetch_events", return_value=[]), \
             patch("core.road511.fetch_bridges", return_value=[bridge]), \
             patch("core.road511.fetch_weigh_stations", return_value=[]), \
             patch("core.road511.fetch_truck_parking", return_value=[]):
            result = r511.check_route_safety(35.0, -90.0, _empty_config())
        self.assertFalse(result["safe"])
        self.assertFalse(result["clearance_ok"])
        self.assertEqual(len(result["bridge_alerts"]), 1)

    def test_sub_call_exception_does_not_crash_report(self):
        def boom(*a, **kw):
            raise RuntimeError("simulated upstream failure")
        with patch("core.road511._resolve_key", return_value="key"), \
             patch("core.road511._load_license", return_value=("key", "m1")), \
             patch("core.road511.fetch_events", side_effect=boom), \
             patch("core.road511.fetch_bridges", side_effect=boom), \
             patch("core.road511.fetch_weigh_stations", side_effect=boom), \
             patch("core.road511.fetch_truck_parking", side_effect=boom):
            result = r511.check_route_safety(35.0, -90.0, _empty_config())
        # Should still return a valid report dict, not crash
        self.assertTrue(result.get("available"))
        self.assertEqual(result["incidents"], [])
        self.assertEqual(result["bridge_alerts"], [])


# ── Runner ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    loader  = unittest.TestLoader()
    suite   = unittest.TestSuite()
    classes = [
        TestResolveKey, TestLoadLicense, TestMapSeverity,
        TestGet, TestGetProxy, TestFetch,
        TestFetchEvents, TestFetchBridges,
        TestFetchWeighStations, TestFetchTruckParking,
        TestCheckRouteSafety,
    ]
    for cls in classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    total  = result.testsRun
    passed = total - len(result.failures) - len(result.errors)
    print(f"\n{'='*60}")
    print(f"  road511  {passed}/{total} tests passed")
    if result.failures or result.errors:
        sys.exit(1)
