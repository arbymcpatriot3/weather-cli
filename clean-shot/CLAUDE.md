# Clean Shot — CLAUDE.md
## Project Context for AI-Assisted Development

**Company:** Blue Collar Nation LLC
**Product:** Clean Shot — weather + road intelligence platform for truck drivers
**Tagline:** Built for the road, not the boardroom.
**Mission:** Truckers first. Everything else follows.
**Version:** 3.0.0 (rewrite from weather-cli v2.0.0)
**Repo:** https://github.com/arbymcpatriot3/weather-cli (branch: main)
**Root:** `clean-shot/` inside the repo

---

## Architecture Rules — Non-Negotiable

```
ASCII + emoji display only       No images, no web views
2G / EDGE capable                Full route refresh < 50 KB
Battery drain < 3% per hour      No background polling abuse
80% functionality offline        Cache-first, network-second
Cold start < 2 seconds           Lazy imports, no heavy init
Truckers first always            Every feature decision goes through this filter
Zero new API keys                Use free/open services only
```

**Data budgets enforced in code:**
| Operation | Budget |
|---|---|
| Full route refresh | < 50 KB |
| Single hazard report | < 200 bytes |
| Background per hour | < 5 KB |
| Reverse geocode cache | 0 bytes (served from /tmp) |

---

## Subscription Tiers

| Tier | Price | Key Features |
|---|---|---|
| free | $0 | Basic weather + NOAA alerts |
| solo_pro | $19.99/mo | All 7 detectors, TTS, GPS, parking, HOS |
| pro_plus | $29.99/mo | Fleet view, API access |
| fleet | $15/seat/mo | Dashboard + dispatch |
| enterprise | custom | White-label |

Feature gating is in `core/subscription.py` → `has_feature(config, feature_name)`.

## Referral Tiers

| Count | Tier | Benefit |
|---|---|---|
| 0-1 | Road Scout | — |
| 2-4 | Captain | 20-40% off |
| 5-9 | Commander | 50-90% off |
| 10-14 | Legend | Free forever |
| 15-24 | Elite | Free forever |
| 25+ | Ambassador | We pay them monthly |

10% off per referral. Free at 10. Paid at 11+. Logic in `core/referral.py`.

---

## Completed Modules

### `core/cache.py`
Extracted from old api.py. Atomic writes (tmp → rename). Stale-fallback on
network loss. Named path helpers: `weather_cache_path`, `alert_cache_path`,
`hazard_cache_path`, `dot511_cache_path`, `parking_cache_path`.

Cache TTLs: weather=10min, alerts=5min, hazards=2min, DOT511=15min.

### `core/api.py`
Open-Meteo weather fetch, NWS alerts, geocoding, IP auto-location.
All requests use `_HEADERS` with User-Agent. Stale cache fallback on
network failure. No API keys.

### `core/parse.py`
Open-Meteo JSON → clean dicts. `parse_current()`, `parse_forecast()`,
`parse_hourly()`. Weather code table (0-99). `degrees_to_dir()` for wind.

### `core/config.py`
Config path: `~/.config/clean-shot.conf`. `_DEFAULTS` dict has every field
with its default. `get_config()` back-fills defaults on load.
`first_run_setup()` interactive wizard. `show_settings()` displays + updates.

**Key config fields added beyond v2.0.0:**
`subscription_tier`, `driver_id`, `referral_code`, `vehicle_type`,
`home_base`, `tts_enabled`, `voice_enabled`, `offline_mode`,
`tts_repeat_suppress_min` (30), `quiet_hours_start/end`,
`tts_speed_aware`, `language` ("en"), `last_gps_lat/lon/time/source`,
`is_driving`.

### `core/weather.py`
All CLI commands + `main()` entry point. Updated imports from new package
paths. Clean Shot branding. `cleanshot` command name. Reads from `core/api`,
`core/parse`, `display/full`, `display/route`.

### `core/alerts.py` ✅ COMPLETE — 32 tests
7 offline detectors against cached Open-Meteo data. Zero extra API calls.

| Alert | Trigger | Severity |
|---|---|---|
| black_ice | 20-34°F + precip ≥ 20% | CRITICAL (≤30°F) / WARNING |
| bridge_freeze | Temp ≤ 38°F | CRITICAL (≤32°F) / WARNING |
| fog | Weather code 45 (fog) / 48 (icy fog) | WARNING / CRITICAL |
| flood | Heavy rain codes + sustained ≥ 60% over 6h | CRITICAL / WARNING / INFO |
| diesel_gel | Coldest of current or next 6h | CRITICAL / WARNING / INFO |
| high_wind | Gusts vs threshold × vehicle_type factor | CRITICAL / WARNING / INFO |
| mudslide | ≥ 80% precip for 3 consecutive hours | WARNING / INFO |

Wind vehicle factors: semi=1.0, box=0.9, flatbed=1.1, tanker=0.85, rv=0.8.
Diesel thresholds: watch=20°F, warning=15°F, critical=0°F.
Returns list sorted CRITICAL → WARNING → INFO.
Helpers: `has_critical(alerts)`, `filter_by_severity(alerts, sev)`,
`diesel_gel_risk(temp_f)` → "none"|"watch"|"warning"|"emergency".

### `core/gps.py` ✅ COMPLETE — 30 tests
Platform dispatch: Linux (gpsd) → Windows (Location API) → iOS (CoreLocation)
→ config fallback with `stale=True`.

**GpsResult dict:** `{lat, lon, accuracy_m, stale, source, timestamp}`

Key functions:
- `haversine(lat1,lon1,lat2,lon2)` → miles (pure math, no libs)
- `bearing(lat1,lon1,lat2,lon2)` → degrees; `bearing_to_cardinal(deg)` → "N/NE/E/..."
- `is_moving(old, new)` → bool (100m = 0.0621 mi threshold)
- `get_poll_interval(config)` → 60s driving / 600s parked
- `get_position(config)` → GpsResult or None
- `update_position(config, result)` → updates config + sets `is_driving`
- `reverse_geocode(lat, lon)` → `{highway, road, city, state, country, raw}`
  Uses Nominatim (OSM). Cached at 0.01° grid (~1.1 km) for 5 min.
- `estimate_mile_marker(lat, lon, highway)` → int or None
  Lookup table for 10 US interstates: I-76, I-80, I-90, I-95, I-40,
  I-10, I-70, I-35, I-65, I-81. Accuracy ±5-10 mi. TODO: FHWA LRS data.
- `describe_location(lat, lon, config, prev_lat, prev_lon)` → i18n string
  e.g. "I-76 Eastbound near MM142" / "I-76 dirección este cerca del MM142"
- `confirm_hazard_location(hazard_lat, hazard_lon, config)` → dict
  Rejects hazard reports > 2.0 miles from driver. Returns `{confirmed, distance_mi, message}`.
- `PollLoop(config, on_position, on_motion_change)` — background thread

### `core/i18n/` ✅ COMPLETE — covered in GPS tests
Lightweight translation engine. No external dependencies.

- `t(key, **kwargs)` → translated string with `{placeholder}` support
- `set_language(lang)` → activate "en" or "es"
- `detect_language()` → auto-detect from LANG/LANGUAGE env → Python locale → "en"
- `is_rtl(lang)` → True for "ar", "he", "fa", "ur" (flag only — rendering TBD)
- `current_language()` → active lang code
- Falls back to English for any missing key; returns key string itself if missing
  everywhere (never crashes)

**Supported:** en (English), es (Spanish)
**RTL flagged for future:** ar, he, fa, ur

JSON files: `core/i18n/en.json`, `core/i18n/es.json`
Keys: `location.*`, `direction.*`, `gps.*`, `hazard.*`, `tts.*`

### `core/tts.py` ✅ COMPLETE — 40 tests
Platform dispatch chain (first working engine wins):
```
Termux (termux-tts-speak) → Linux (pyttsx3) → Windows (SAPI) →
iOS/macOS (AVSpeechSynthesizer/say) → terminal print fallback
```
Terminal fallback always returns True — TTS never crashes the app.

**Severity routing:**
- CRITICAL → speak immediately, bypass queue, bypass quiet hours (by default)
- WARNING → queued while driving; spoken when parked or `flush_queue()` called
- INFO → queued only; never auto-fires

**Repeat suppression:** keyed by `alert_type` → `{time, text_hash}`.
Re-alerts automatically when text changes (conditions escalated = new hash).
`clear_suppression(alert_type=None)` to reset.

**Distance triggers:** `distance_to_severity(mi)` → 5mi=CRITICAL, 20mi=WARNING, 50mi=INFO.
Ready for hazards.py / dot511.py to pass `distance_mi` to `speak_alert()`.

**Key functions:**
- `speak(text, config, bypass_quiet=False)` — low-level dispatch
- `speak_alert(alert_type, severity, config, distance_mi, force)` — smart dispatch
- `queue_warning(alert_type, config)` — explicit queue
- `flush_queue(config, max_alerts=3)` — speak queued alerts; alias `speak_queued`
- `speak_all_active(alerts, config)` — takes alerts.py output list
- `clear_suppression(alert_type=None)` — reset suppression cache
- `queue_status(config)` → debug dict with platform, BT, queue depth, etc.
- `set_wake_callback(fn)` / `simulate_wake(cmd)` — Phase 2 hook
- `WAKE_PHRASE = "Hey Clean Shot"`

**Language:** English → CB radio strings from `claude/prompts.py`.
Spanish → professional dispatcher tone in `es.json`.
All 16 alert types covered in both languages.

**New config fields:** `tts_repeat_suppress_min=30`, `quiet_hours_start/end`,
`tts_speed_aware=True`.

### `display/full.py`
Migrated from display.py. All non-route display functions.
`get_width()`, `print_header()`, `display_current()`, `display_alerts()`,
`display_wind_alert()`, `display_hourly()`, `display_forecast()`,
`display_rain_timeline()`, `display_regional()`.

### `display/route.py`
Route display functions: `display_route_header()`, `display_route_stop()`.

### `claude/prompts.py`
All Claude prompt templates + CB voice strings.
`_CB_VOICE_ALERTS` dict — 16 types.
`cb_voice_alert(alert_type)` → string or "".
Prompts for: hazard parsing, pattern detection, weekly digest.

### `claude/parser.py`
`parse_hazard_report(text, api_key)` → structured dict.
Offline keyword fallback always available (no API key needed).
Claude API path stubbed.

### `core/subscription.py`
`has_feature(config, feature_name)` → bool. Feature→tier mapping.
Referral count ≥ 10 upgrades free tier to solo_pro automatically.
`get_upgrade_message(feature)` for gated feature prompts.

### `core/referral.py`
Full tier/discount math. `get_tier(count)`, `calc_discount_pct(count)`,
`is_free_tier(count)`, `is_ambassador(count)`.
`get_referral_link(config)`, `get_referral_stats(config)`.
`display_referral_card(config)` → ASCII stats card.

### `platforms/linux/main.py`
Entry point. Adds clean-shot/ to sys.path, calls `core.weather.main()`.
Run: `python platforms/linux/main.py`

### `platforms/linux/install.sh`
Downloads all package files, installs deps, creates `~/.local/bin/cleanshot` launcher.

---

## Test Inventory — 102 Tests / 5 Suites

| Suite | File | Tests | Status |
|---|---|---|---|
| Alerts | tests/test_alerts.py | 32 | ✅ |
| GPS | tests/test_gps.py | 30 | ✅ |
| TTS | tests/test_tts.py | 40 | ✅ |
| Referral | tests/test_referral.py | 4 | ✅ |
| Hazards | tests/test_hazards.py | 3 | ✅ |

Run all: `cd clean-shot && python3 tests/test_alerts.py && python3 tests/test_gps.py && python3 tests/test_tts.py && python3 tests/test_referral.py && python3 tests/test_hazards.py`

---

## Build Queue — Next Modules

Build one module at a time. Always ask before starting the next one.

| # | Module | Key Requirement |
|---|---|---|
| 1 | `core/hazards.py` | Community reports + GPS clustering + Claude parser |
| 2 | `core/dot511.py` | DOT/511 feeds all 50 states |
| 3 | `core/parking.py` | Smart runway — miles until forced stop |
| 4 | `core/hos.py` | FMCSA 11/14/70-hour rules, advisory only |
| 5 | `core/feedback.py` | Driver report submission + upvote/dismiss |
| 6 | `core/savings.py` | Time + money saved tracker + shareable ASCII cards |
| 7 | `core/referral.py` | Viral engine (stub → full; backend integration) |
| 8 | `display/glance.py` | 2-second glance mode, max 6 lines, no scroll |
| 9 | `platforms/windows/main.py` | Windows-specific startup + SAPI init |
| 10 | `platforms/ios/main.py` | iOS-specific startup + CoreLocation init |

---

## Key Technical Decisions (Don't Re-Debate These)

**Offline-first.** Every module checks local cache before any network call.
Network failure must never crash the app — always degrade gracefully.

**No new API keys.** Open-Meteo (weather), NWS (alerts), Nominatim (geocode),
ipapi.co (IP location). All free, no registration.

**config dict is the source of truth** for runtime state. Pass it around.
Save with `save_config(config)` after mutations. Never store mutable state
in module globals that needs to survive across sessions.

**Subscription gating** goes through `core/subscription.has_feature()` only.
Never hard-code tier checks inline — always call `has_feature()`.

**TTS suppression** is keyed by `alert_type` + text hash. Same type with
different text (escalated severity) re-alerts automatically. This is intentional.

**GPS stale fallback.** `stale=True` in GpsResult means position is from
config, not live. Callers display "(stale)" indicator but don't crash.

**i18n:** English gets CB radio culture. Spanish gets professional dispatcher
tone. Other languages fall back to English. `t()` never crashes — returns
key string if translation missing.

**All CB voice strings** in `claude/prompts.py` `_CB_VOICE_ALERTS`. The TTS
module reads from there for English. `es.json` `tts.*` keys for Spanish.
Never put voice strings inline in feature modules.

**Tests run offline** — no GPS hardware, no network, no audio output.
Mock platform behavior by setting `tts_enabled=False`, `offline_mode=True`.

---

## File Structure

```
clean-shot/
├── CLAUDE.md                  ← you are here
├── requirements.txt           ← requests, colorama (+ optional per-platform)
├── core/
│   ├── weather.py             ✅ migrated — CLI commands + main()
│   ├── api.py                 ✅ migrated — Open-Meteo, NWS, geocoding
│   ├── parse.py               ✅ migrated — Open-Meteo JSON parser
│   ├── config.py              ✅ enhanced — all settings + GPS + TTS fields
│   ├── cache.py               ✅ extracted — atomic writes, stale fallback
│   ├── alerts.py              ✅ COMPLETE — 7 detectors, 32 tests
│   ├── gps.py                 ✅ COMPLETE — dispatch + polling + geo-confirm, 30 tests
│   ├── tts.py                 ✅ COMPLETE — 5 platforms + smart queue, 40 tests
│   ├── subscription.py        ✅ tier gating
│   ├── referral.py            ✅ tier/discount math (backend stub)
│   ├── compress.py            stub — data minimization
│   ├── hazards.py             stub — community reports
│   ├── dot511.py              stub — DOT/511 feeds
│   ├── parking.py             stub — smart runway
│   ├── hos.py                 stub — HOS guardian
│   ├── health.py              stub — driver wellness
│   ├── feedback.py            stub — driver reports
│   ├── voice.py               stub — Hey Clean Shot (Phase 2)
│   └── i18n/
│       ├── __init__.py
│       ├── translator.py      ✅ t(), set_language(), is_rtl()
│       ├── en.json            ✅ English — CB radio strings
│       └── es.json            ✅ Spanish — dispatcher tone
├── display/
│   ├── full.py                ✅ migrated — current/hourly/forecast/alerts
│   ├── route.py               ✅ migrated — route header + stop display
│   ├── glance.py              stub — 2-second glance mode
│   ├── dashboard.py           stub — fleet view
│   └── themes.py              stub — nighthawk/highvis/minimal/cb
├── claude/
│   ├── prompts.py             ✅ 16 CB voice strings + 3 Claude prompts
│   ├── parser.py              ✅ offline keyword fallback + Claude stub
│   ├── patterns.py            stub — cluster detection
│   └── digest.py              stub — weekly summary
├── platforms/
│   ├── linux/
│   │   ├── main.py            ✅ entry point
│   │   ├── install.sh         ✅ installer
│   │   ├── tts_linux.py       ✅ pyttsx3
│   │   └── gps_linux.py       ✅ gpsd
│   ├── windows/
│   │   ├── main.py            stub
│   │   ├── tts_windows.py     ✅ SAPI
│   │   ├── gps_windows.py     ✅ WinRT
│   │   ├── install.ps1        stub
│   │   └── cleanshot.bat      ✅ launcher
│   └── ios/
│       ├── main.py            stub
│       ├── tts_ios.py         ✅ AVSpeechSynthesizer
│       ├── gps_ios.py         ✅ CoreLocation
│       └── README_ios.md      ✅
└── tests/
    ├── test_alerts.py         ✅ 32 tests
    ├── test_gps.py            ✅ 30 tests
    ├── test_tts.py            ✅ 40 tests
    ├── test_referral.py       ✅ 4 tests
    └── test_hazards.py        ✅ 3 tests
```

---

## CB Voice String Style Guide

All CB voice strings follow this pattern. Apply it when writing new ones.

```
✅ "Smokey's reporting black ice ahead good buddy — back it down"
✅ "Got some hammer lane wind at your door — watch that trailer"
✅ "Breaker breaker — temps are dropping, your diesel might be gelling up"

❌ "Warning: black ice detected on roadway"   ← too corporate
❌ "Attention driver, wind speed is elevated"  ← too robotic
❌ "Please be careful, there may be ice"       ← too weak
```

Rules:
- CB radio lingo: "breaker", "good buddy", "driver", "roger that", "10-4"
- Always end with a concrete action: "back it down", "watch that trailer",
  "find a chicken coop", "park it if you can"
- Friendly, never panicked — even CRITICAL alerts stay calm and direct
- Under 120 characters — fits in one TTS breath
- English only for CB strings; Spanish gets professional dispatcher tone

---

*This file is auto-loaded by Claude Code in every session.*
*Update it when a module is completed or a key decision changes.*
*Last updated: 2026-04-06 — modules through core/tts.py complete.*
