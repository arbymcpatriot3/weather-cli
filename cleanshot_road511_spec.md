# CleanShot v3.0.7 — Road511 Integration Spec
## Implementation guide for Claude Code

---

## Context

CleanShot is a Python CLI trucking intelligence app (`clean-shot/core/`).
It currently fetches DOT/511 road incidents via `core/dot511.py` using a basic
lat/lon radius query against the Road511 API. The account has been upgraded to
the **Starter plan** ($29/mo), which unlocks all 65 jurisdictions, GeoJSON bulk
export, and the trucking/freight endpoints.

The goal of this sprint is to make CleanShot genuinely tell a trucker whether
their route is safe — not just "any incidents nearby" but bridge clearances,
weight limits, weigh station status, truck parking availability, live cameras,
and real-time hazard events along a full route corridor.

---

## Files to Modify

| File | Change type |
|------|------------|
| `core/dot511.py` | Major rewrite |
| `core/cache.py` | Add new cache paths + TTLs |
| `core/config.py` | Add new config keys |
| `core/display.py` | Add Road511 display functions |
| `core/parking.py` | Augment with Road511 truck parking |
| `core/subscription.py` | Add new feature flags |

## New File to Create

| File | Purpose |
|------|---------|
| `core/road511.py` | All Road511 API logic, separated cleanly from dot511.py |

---

## 1. `core/cache.py` — Add new cache paths and TTLs

```python
BRIDGE_CACHE_TIME   = 86400   # 24h — bridge clearances rarely change
TRUCK_ROUTE_CACHE   = 3600    # 1h  — route data
CAMERA_CACHE_TIME   = 120     # 2min — cameras are near-live
FEATURE_CACHE_TIME  = 900     # 15min — weigh stations, parking, etc.

def bridge_cache_path(lat: float, lon: float) -> Path:
    return _cache_path(lat, lon, "_bridges")

def route_cache_path(origin_lat, origin_lon, dest_lat, dest_lon) -> Path:
    key = hashlib.sha256(
        f"{origin_lat:.3f},{origin_lon:.3f},{dest_lat:.3f},{dest_lon:.3f}".encode()
    ).hexdigest()[:16]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"cs_{key}_route.json"

def feature_cache_path(lat: float, lon: float, ftype: str) -> Path:
    return _cache_path(lat, lon, f"_{ftype}")
```

---

## 2. `core/config.py` — Add new config keys to `_DEFAULTS`

Add these keys to the `_DEFAULTS` dict:

```python
# Road511
"road511_api_key":       None,       # set during setup or env var R511_API_KEY
"road511_enabled":       True,
"road511_radius_km":     80,         # ~50 miles

# Vehicle dims for bridge/clearance checks
"vehicle_height_ft":     13.5,       # already exists — confirm default
"vehicle_weight_lbs":    80000,      # gross vehicle weight (legal max)
"vehicle_length_ft":     75,         # total rig length

# Route safety
"last_route_origin":     None,       # "lat,lon" or city string
"last_route_dest":       None,

# Feature preferences
"show_cameras":          False,      # off by default (bandwidth)
"show_weigh_stations":   True,
"show_bridge_warnings":  True,
"show_truck_parking":    True,
```

Also add to `first_run_setup()` — after the vehicle type question, ask:

```
4. Your vehicle height? (for bridge clearance warnings)
   Press Enter to use standard 13'6" semi height:
   > _
```

And add to `handle_settings()`:
```
cleanshot settings height 13.5        Set vehicle height in feet
cleanshot settings weight 80000       Set GVW in pounds
cleanshot settings road511-key <key>  Set Road511 API key
cleanshot settings cameras on|off     Show live camera links
```

---

## 3. `core/road511.py` — New file (primary Road511 client)

Create this as a clean, standalone module. Import it from `dot511.py`.

### 3a. Constants

```python
_BASE = "https://api.road511.com/api/v1"
_HEADERS = {"User-Agent": "clean-shot/3.0 (cleanshothq@pm.me)"}

def _h(key: str) -> dict:
    return {"X-API-Key": key, **_HEADERS}
```

### 3b. `fetch_events(lat, lon, config)` → `list[dict]`

Already partially implemented in `dot511.py`. Move here and clean up:
- Use `?lat=&lon=&radius_km=&status=active`
- Parse `properties` block into normalized CleanShot incident format
- Filter to ≤ 20 events
- Cache 15 min via `dot511_cache_path`

Normalized incident dict:
```python
{
    "source":        "road511",
    "type":          str,   # incident | construction | closure | weather | chain_control | weight_restriction
    "severity":      str,   # critical | major | moderate | minor
    "road":          str,   # "I-80", "US-30"
    "direction":     str,
    "description":   str,   # truncated to 120 chars
    "truck_relevant": bool,
    "expires":       str | None,
    "risk_score":    int,   # assigned by filter_truck_relevant()
}
```

### 3c. `fetch_bridges(lat, lon, config)` → `list[dict]`  ⭐ KEY FEATURE

```
GET /api/v1/features?type=bridge_clearances&lat=&lon=&radius_km=
```

Parse each bridge feature into:
```python
{
    "source":        "road511_nbi",
    "type":          "bridge_clearance",
    "road":          str,
    "name":          str | None,
    "clearance_ft":  float,
    "weight_limit_tons": float | None,
    "lat":           float,
    "lon":           float,
    "flagged":       bool,   # True if clearance_ft < vehicle_height_ft + 0.5 margin
}
```

**Critical**: flag any bridge where `clearance_ft < config["vehicle_height_ft"] + 0.5`.
The 0.5 ft margin accounts for load shifts and road surface variations.

Cache 24 hours via `bridge_cache_path`. Bridges don't change daily.

### 3d. `fetch_truck_routing(origin, destination, config)` → `dict`  ⭐ KEY FEATURE

```
POST /api/v1/routing/truck
Body: {
    "origin": {"lat": float, "lon": float},
    "destination": {"lat": float, "lon": float},
    "vehicle": {
        "height_ft":   config["vehicle_height_ft"],
        "weight_lbs":  config["vehicle_weight_lbs"],
        "length_ft":   config["vehicle_length_ft"],
        "type":        config["vehicle_type"]   # "semi"
    }
}
```

Returns a route-safe result. Cache 1 hour via `route_cache_path`.

Parse response into:
```python
{
    "safe":            bool,
    "warnings":        list[str],    # human-readable issues
    "bridge_alerts":   list[dict],   # bridges on route below clearance
    "weight_alerts":   list[dict],   # weight-restricted segments
    "distance_miles":  float,
    "duration_min":    float,
    "staa_route":      bool,         # True if on STAA-designated network
}
```

### 3e. `fetch_weigh_stations(lat, lon, config)` → `list[dict]`

```
GET /api/v1/features?type=weigh_stations&lat=&lon=&radius_km=50
```

Parse into:
```python
{
    "source":    "road511",
    "type":      "weigh_station",
    "name":      str,
    "road":      str,
    "direction": str,
    "status":    str,    # "open" | "closed" | "unknown"
    "distance_miles": float,   # compute from haversine vs driver lat/lon
    "lat":       float,
    "lon":       float,
}
```

Cache 15 min. Filter to within 50 miles, sorted by distance.

### 3f. `fetch_truck_parking(lat, lon, config)` → `list[dict]`

```
GET /api/v1/features?type=truck_parking&lat=&lon=&radius_km=50
```

CleanShot already has `core/parking.py` with Overpass-based stops. Road511 data
is higher quality. Merge Road511 results with existing embedded stops:

```python
{
    "source":      "road511",
    "name":        str,
    "road":        str,
    "spaces":      int | None,
    "amenities":   list[str],   # ["diesel", "shower", "wifi", "restaurant"]
    "lat":         float,
    "lon":         float,
    "distance_miles": float,
}
```

### 3g. `fetch_cameras(lat, lon, config)` → `list[dict]`

Only fetch if `config["show_cameras"]` is True (off by default — bandwidth concern).

```
GET /api/v1/features?type=cameras&lat=&lon=&radius_km=30
```

Parse into:
```python
{
    "source":     "road511",
    "type":       "camera",
    "road":       str,
    "direction":  str,
    "image_url":  str,
    "distance_miles": float,
}
```

### 3h. `check_route_safety(lat, lon, config)` → `dict`  ⭐ MAIN ORCHESTRATOR

This is the top-level function that answers "is my route safe?". It runs all
relevant checks and returns a unified safety report:

```python
def check_route_safety(lat: float, lon: float, config: dict) -> dict:
    """
    Full route safety check for the current position.
    Returns a safety report dict — display with display_route_safety().
    """
    key = config.get("road511_api_key")
    if not key:
        return {"available": False, "reason": "no_api_key"}

    report = {
        "available":      True,
        "safe":           True,          # flips False if any critical issue found
        "clearance_ok":   True,
        "weight_ok":      True,
        "incidents":      [],
        "bridge_alerts":  [],
        "weigh_stations": [],
        "truck_parking":  [],
        "cameras":        [],
        "warnings":       [],            # human-readable summary lines
        "critical":       [],            # items requiring immediate attention
    }

    # 1. Active incidents
    incidents = fetch_events(lat, lon, config)
    report["incidents"] = incidents
    critical_incidents = [i for i in incidents if i.get("severity") in ("critical", "major")]
    if critical_incidents:
        report["safe"] = False
        report["critical"].extend([i["description"] for i in critical_incidents[:3]])

    # 2. Bridge clearances
    height = config.get("vehicle_height_ft", 13.5)
    bridges = fetch_bridges(lat, lon, config)
    flagged = [b for b in bridges if b.get("flagged")]
    report["bridge_alerts"] = flagged
    if flagged:
        report["safe"] = False
        report["clearance_ok"] = False
        for b in flagged[:3]:
            report["critical"].append(
                f"LOW CLEARANCE: {b['road']} bridge — {b['clearance_ft']:.1f} ft "
                f"(your vehicle: {height:.1f} ft)"
            )

    # 3. Weigh stations
    report["weigh_stations"] = fetch_weigh_stations(lat, lon, config)

    # 4. Truck parking (top 5 closest)
    report["truck_parking"] = fetch_truck_parking(lat, lon, config)[:5]

    # 5. Cameras (if enabled)
    if config.get("show_cameras"):
        report["cameras"] = fetch_cameras(lat, lon, config)

    return report
```

---

## 4. `core/dot511.py` — Refactor to use `road511.py`

Keep all the existing NWS + state feed code intact. The refactor is additive:

```python
from core.road511 import fetch_events as _r511_events, check_route_safety

def fetch_dot511(lat: float, lon: float, config: dict = None) -> list:
    if config is None:
        config = get_config()

    incidents = []

    # Priority 1: Road511 (best quality, Starter plan)
    if config.get("road511_enabled") and config.get("road511_api_key"):
        incidents.extend(_r511_events(lat, lon, config))

    # Priority 2: NWS weather advisories (free fallback)
    if not incidents or len(incidents) < 3:
        features = _fetch_nws_features(lat, lon)
        incidents.extend(parse_nws_features(features))

    # Priority 3: State feeds (legacy fallback)
    if not incidents:
        state = _lat_lon_to_state(lat, lon)
        if state:
            incidents.extend(_fetch_state_feed(state, config))

    return filter_truck_relevant(incidents, config)
```

Fix the broken `ImportError` fallback at the top of the file:
```python
# Replace:
from cache import ...  # broken

# With:
try:
    from core.cache import cache_load, cache_save, cache_stale, dot511_cache_path, DOT511_CACHE_TIME
    from core.config import get_config
except ImportError:
    from cache import cache_load, cache_save, cache_stale, dot511_cache_path, DOT511_CACHE_TIME
    from config import get_config
```

Also fix the unused `height` variable in `filter_truck_relevant` — it's read
from config but never used in the scoring. Either use it (check bridge-related
keywords against `height`) or remove it.

---

## 5. `core/display.py` — New display functions

Add these display functions at the bottom of `display.py`:

### `display_route_safety(report, config, width)`

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  🚛 ROUTE SAFETY CHECK                                                       │
└──────────────────────────────────────────────────────────────────────────────┘

  ✅ Route appears CLEAR  (or)  🚨 HAZARDS DETECTED

  Bridge Clearances
  ─────────────────
  ⚠  I-80 WB overpass — 13.2 ft clearance  (your rig: 13.5 ft)  LOW CLEARANCE
  ✓  All other bridges within 50 mi: OK

  Active Incidents
  ────────────────
  [M] I-76 EB — Construction, 2 lanes closed near mile marker 142
      Risk: 80/100

  Weigh Stations (next 50 mi)
  ───────────────────────────
  OPEN   I-80 WB — Cheyenne Port of Entry  (12 mi)
  CLOSED I-80 EB — Pine Bluffs  (8 mi)

  Truck Parking (nearest 5)
  ─────────────────────────
  Pilot Travel Center — I-80 Exit 34  (6 mi)
  Love's — US-30 MM 214  (14 mi)
```

Use existing `Fore.RED` / `Fore.YELLOW` / `Fore.GREEN` color conventions from
`display.py`. Follow the `separator()` and `print_header()` patterns already
in the file.

### `display_bridge_alerts(bridges, vehicle_height_ft, width)`

Standalone bridge-only display for use in TTS module too.

### `display_weigh_stations(stations, width)`

Simple open/closed list with distance.

---

## 6. `core/subscription.py` — New feature flags

Add to `_FEATURE_TIER`:
```python
"route_safety":      "solo_pro",
"bridge_clearances": "solo_pro",
"weigh_stations":    "solo_pro",
"road511_routing":   "solo_pro",
"live_cameras":      "solo_pro",
```

---

## 7. `core/parking.py` — Augment with Road511 data

In `get_parking_options()`, after fetching Overpass results, merge Road511 truck
parking if key is available:

```python
from core.road511 import fetch_truck_parking

def get_parking_options(lat, lon, config):
    # ... existing Overpass + embedded logic ...

    # Augment with Road511 data (higher quality)
    if config.get("road511_api_key") and config.get("road511_enabled"):
        r511_stops = fetch_truck_parking(lat, lon, config)
        # Merge, dedup by proximity (< 0.1 mi = same stop)
        stops = _merge_parking_stops(stops, r511_stops)

    return sorted(stops, key=lambda s: s.get("distance_miles", 999))
```

Add `_merge_parking_stops(a, b)` helper that deduplicates by lat/lon proximity.

---

## 8. CLI entry point — New `cleanshot route` command

In `clean-shot.py` (or wherever CLI args are handled), add:

```
cleanshot route                   Full safety check at current location
cleanshot route <dest>            Truck-safe routing to destination
cleanshot bridges                 Bridge clearances within 50 miles
cleanshot weigh                   Weigh station status ahead
```

`cleanshot route` should call `check_route_safety()` and `display_route_safety()`.

`cleanshot route "Denver CO"` should also call `fetch_truck_routing()` with
current lat/lon as origin and geocoded destination.

---

## 9. TTS integration — Speak critical route alerts

In `core/tts.py`, add Road511 alerts to the spoken briefing. The TTS module
already has severity-based queuing. Add these alert types:

```python
"bridge_clearance": "CRITICAL",   # always speak — safety critical
"weigh_open":       "INFO",
"road_closure":     "WARNING",
"chain_control":    "WARNING",
"weight_restrict":  "WARNING",
```

Bridge clearance alerts should fire regardless of quiet hours (safety exception).
Follow the existing `_should_suppress()` pattern but add a `force=True` param.

---

## Implementation Order

1. `core/cache.py` — add paths/TTLs (5 min)
2. `core/config.py` — add keys + setup question (10 min)
3. `core/road511.py` — create from scratch (45 min)
4. `core/dot511.py` — refactor to import road511 (15 min)
5. `core/display.py` — add display functions (20 min)
6. `core/parking.py` — augment with Road511 data (15 min)
7. `core/subscription.py` — add feature flags (5 min)
8. CLI entry point — add new commands (15 min)
9. TTS integration (15 min)

Total estimated: ~2.5 hours for Claude Code

---

## Testing Checklist

After implementation, verify:

- [ ] `cleanshot route` runs without error, shows safety report
- [ ] Bridge alert fires when `clearance_ft < vehicle_height_ft + 0.5`
- [ ] No crash when `road511_api_key` is None (graceful fallback to NWS)
- [ ] Cache files written to tmp dir, not repo
- [ ] `filter_truck_relevant()` no longer has unused `height` variable
- [ ] `from cache import ...` broken fallback is fixed
- [ ] All new config keys present in `_DEFAULTS`
- [ ] `has_feature(config, "bridge_clearances")` returns True on trial/solo_pro
- [ ] `cleanshot route "Chicago IL"` produces truck routing output
- [ ] TTS speaks bridge clearance alert even during quiet hours

---

## Notes for Claude Code

- **API key**: already in `config.py` as `r511_ce239b2c70f846b3da9c4949c6082f9d35422c5422d29bff95e2d963ad0a5d1a`. Read via `config.get("road511_api_key")` or fall back to `os.environ.get("R511_API_KEY")`.
- **Starter plan limits**: 300 RPM, 50k req/day, all 65 jurisdictions. Respect the cache TTLs above — don't hammer the API.
- **Fail open**: like the rest of CleanShot, all Road511 calls must fail silently. A network error should never crash the app or block a trucker.
- **Data budget**: Road511 events response ≈ 5–15 KB. Bridge features ≈ 10–30 KB. Truck routing ≈ 2–5 KB. All well within the 50 KB full-refresh budget.
- **haversine**: already available in `core/gps.py` — import it for distance calculations.
- **Existing patterns**: follow `parking.py` for structure (it's the most complete module). Follow `display.py` color conventions exactly.
- **Don't break existing tests**: NWS + state feed fallback paths in `dot511.py` must still work when `road511_api_key` is None.
