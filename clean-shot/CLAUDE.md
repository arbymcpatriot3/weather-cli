# Clean Shot — CLAUDE.md
## Project Context for AI-Assisted Development

**Company:** Blue Collar Nation LLC
**Product:** Clean Shot — Driver Intelligence System (CSDIS)
**Tagline:** Built for the road, not the boardroom.
**Mission:** Truckers first. Everything else follows.
**Version:** 3.0.0 (rewrite from weather-cli v2.0.0)
**Website:** cleanshothq.com (coming soon)
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
Termux (termux-tts-speak) → Linux (piper→festival→pyttsx3) → Windows (SAPI) →
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

### `core/hazards.py` ✅ COMPLETE — 31 tests
Community hazard reports: submit, store, filter, cluster, and speak.
Tier: solo_pro+ (`has_feature(config, "community_hazards")`).

**Data budget:** < 200 bytes per report (enforced in `submit_hazard()`).
**Local store:** `/tmp/clean-shot-cache/hazards_community.json` (atomic writes).
**Backend sync:** Phase 2 stub (`_sync_to_backend()`).

Key constants: `CLUSTER_MIN_REPORTS=2`, `CLUSTER_RADIUS_MI=10.0`,
`CLUSTER_WINDOW_MIN=60`, `MAX_HAZARD_AGE_H=4`.

**HazardReport dict keys:** `t, lat, lon, ts, sev, dir, src, clr, note`

Key functions:
- `submit_hazard(lat, lon, hazard_type, description, config)` → bool
  Parses description offline → stores report locally → queues backend sync
- `get_nearby_hazards(lat, lon, radius_miles, config)` → list
  Filters by distance + age + cleared; sorted closest first
- `expire_old_hazards(reports)` → list  (in-memory, no disk write)
- `cluster_reports(reports)` → list of cluster dicts
  Groups same-type within CLUSTER_RADIUS_MI + CLUSTER_WINDOW_MIN.
  Emits worst severity. Requires >= CLUSTER_MIN_REPORTS.
- `get_active_hazards(lat, lon, config)` → list
  Nearby + clustered, subscription-gated, sorted by distance
- `parse_hazard_text(text, config)` → dict  (delegates to claude/parser.py)
- `hazard_to_alert_type(hazard_type)` → TTS alert type string
- `severity_to_tts(sev_str)` → "CRITICAL" | "WARNING" | "INFO"
- `speak_nearby_hazards(hazards, config)` → int (routes to tts.speak_alert)
- `display_hazards(hazards, config)` → ASCII, max 5 shown
- `clear_local_store()` → erase all local reports (testing + factory reset)

**Integration wiring:**
- `haversine()` from core.gps (no duplicate math)
- `parse_hazard_report()` from claude.parser (offline always available)
- `has_feature()` from core.subscription (community_hazards = solo_pro+)
- TTS via `from core.tts import speak_alert` (lazy import inside function)

### `core/dot511.py` ✅ COMPLETE — 41 tests
DOT/511 road condition feeds. Tier: solo_pro+ (`has_feature(config, "dot511")`).

**Primary source:** NWS `api.weather.gov/alerts/active?point={lat},{lon}` — free,
no key, all 50 states. Covers: winter weather, chains, fog, flooding, high wind,
ice, blizzards, avalanche, dust storms, special weather statements.

**State feeds framework:** `STATE_FEEDS` dict — all 51 slots (50 + DC), all None
until confirmed-free public feeds become available. `_fetch_state_feed()` is the
integration point. Add URL to STATE_FEEDS dict when a state publishes open data.

**Incident dict keys:** `type, severity, highway, direction, description, source,
expires, truck_only`

**Incident types:** `weather_advisory | chains_required | closure | construction |
bridge_restriction | weigh_station | incident`

Key helpers (all pure, offline-testable):
- `_has_chain_requirement(text)` → bool — detects chain/traction keywords
- `_extract_highway(text)` → "I-70" | "US-40" | None — regex with normalization
- `_extract_direction(text)` → "northbound" | ... | "unknown"
- `_nws_event_to_type(event_name)` → incident type string
- `_nws_severity(nws_sev, urgency)` → "low"|"medium"|"high"|"critical"
- `_lat_lon_to_state(lat, lon)` → state code or None (bounding box, ±30-50mi)
- `_iso_to_unix(iso_str)` → int | None
- `_truncate_desc(text, 100)` → <= 100 chars at word boundary

Key public functions:
- `parse_nws_features(features)` → incident list
- `filter_truck_relevant(incidents, config)` → filtered list
- `fetch_dot511(lat, lon, config)` → NWS + state feed, cached 15min
- `get_active_incidents(lat, lon, config)` → gated + sorted critical-first
- `speak_dot511_alerts(incidents, config)` → int (routes to tts.speak_alert)
- `display_dot511(incidents, config)` → ASCII, max 8 shown

**Cache:** `dot511_cache_path(lat, lon)`, 15-min TTL (DOT data slow-changing).
Stale fallback on network loss — never crashes.

### `core/hos.py` ✅ COMPLETE — 49 tests
FMCSA Hours of Service guardian. Tier: solo_pro+ (`has_feature(config, "hos_guardian")`).
**Advisory only — not an ELD replacement.** Driver responsible for FMCSA compliance.

**FMCSA rules implemented:**
11-hour driving limit, 14-hour on-duty wall clock, 30-min break after 8h driving,
60h/7-day or 70h/8-day weekly limit, 10-hour reset.

**State stored in config dict** (prefixed `hos_`). Persisted by `save_config()`.
Key fields: `hos_session_start_ts`, `hos_drive_elapsed_min`, `hos_drive_start_ts`,
`hos_break_drive_min`, `hos_is_driving`, `hos_is_on_duty`, `hos_7day_duty_min`, `hos_cycle`.
Writes `hos_drive_remaining_min` → parking.py reads this for runway calc.

**Time mockable via `hos._time_fn`** — test-safe, fully offline.

Key functions:
- `get_hos_status(config)` → full status dict; writes `hos_drive_remaining_min` side effect
- `start_drive(config)` / `stop_drive(config)` — accumulate drive segments
- `start_duty(config)` / `end_duty(config)` — manage 14h wall clock window
- `take_break(config)` — reset break counter (>= 30 min off duty)
- `reset_hos(config)` — full 10h reset; clears all windows
- `update_elapsed(config)` — refresh parking feed without state change (watch loop)
- `needs_break(config)` → bool; `minutes_until_break_required(config)` → float
- `add_duty_to_weekly(config, min)`, `reset_weekly(config)`, `get_weekly_remaining(config)`
- `check_hos_thresholds(config)` → list of crossed thresholds (pure, no side effects)
- `announce_hos(config)` → int — speaks newly-crossed thresholds via TTS (once per trip)
- `reset_announcements()` — clear per-trip TTS tracking
- `format_hos_str(status)` → compact one-line summary string
- `display_hos_status(config)` — full ASCII status block

`_urgency_level(minutes)`: >60=normal, 31-60=warning, 16-30=urgent, <=15=critical

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
Unified Linux entry point. Pre-flight dependency check, sys.path setup,
error handling with `CLEANSHOT_DEBUG=1` traceback mode.
Passes all CLI args through to `core.weather.main()`.
Run: `python3 platforms/linux/main.py`
Full unified view (no args): weather + alerts + DOT/511 + hazards + parking + HOS.

### `platforms/linux/install.sh`
Fully hands-free. Auto-installs: Python 3+, pip, git, espeak-ng + festival
(TTS fallback), pyttsx3, requests, colorama, piper-tts (neural TTS).
Downloads `en_US-lessac-medium` voice model (~60MB) to `~/.local/share/piper/`.
Creates launcher at `/usr/local/bin/cleanshot` (falls back to `~/.local/bin`).
Runs doctor at end. Zero manual steps.

### `platforms/macos/install.sh` ✅ REWRITTEN — hands-free
Fully hands-free. Steps: Xcode CLT (with wait loop) → Homebrew (friendly
password/time message) → Python 3.11 via brew → Git → git clone/pull →
pip packages → launcher at `/usr/local/bin/cleanshot`. Detects Apple Silicon
vs Intel for PATH (.zprofile). Zero manual steps.

### `platforms/windows/install.ps1` ✅ REWRITTEN — hands-free
Fully hands-free. Auto-installs Python 3.11 + Git via winget. pip packages:
requests, colorama, pywin32. Creates cleanshot.bat + PowerShell function.
Zero manual steps.

### `platforms/android/install_termux.sh` ✅ REWRITTEN — hands-free
Fully hands-free inside Termux. pkg install python git termux-api → pip
requests colorama → git clone → launcher at ~/bin/cleanshot → PATH fixed in
.bashrc. Zero manual steps after pasting the one line.

### `platforms/ios/install_ish.sh` ✅ REWRITTEN — hands-free
Fully hands-free inside iSH. apk install python3 py3-pip git curl → pip
requests colorama → git clone → launcher → profile sourced at end so
`cleanshot` works immediately without `. ~/.profile`. Zero manual steps.

---

## Python Version Compatibility

**Minimum supported: Python 3.8.** Tested on Python 3.9 (macOS system Python).

`core/gps.py`, `core/dot511.py`, `core/parking.py` use `from __future__ import annotations`
so `X | None` type hints work on Python 3.9. All other modules are 3.8+ compatible.

---

## Test Inventory — 357 Tests / 10 Suites

| Suite | File | Tests | Status |
|---|---|---|---|
| Alerts | tests/test_alerts.py | 32 | ✅ |
| GPS | tests/test_gps.py | 30 | ✅ |
| TTS | tests/test_tts.py | 40 | ✅ |
| Tones + Voice + Repeat | tests/test_tones.py | 80 | ✅ |
| Referral | tests/test_referral.py | 4 | ✅ |
| Hazards | tests/test_hazards.py | 31 | ✅ |
| DOT/511 | tests/test_dot511.py | 41 | ✅ |
| Parking | tests/test_parking.py | 39 | ✅ |
| Display Alerts | tests/test_display_alerts.py | 40 | ✅ |
| HOS Guardian | tests/test_hos.py | 49 | ✅ |

Run all: `cd clean-shot && python3 tests/test_alerts.py && python3 tests/test_gps.py && python3 tests/test_tts.py && python3 tests/test_tones.py && python3 tests/test_referral.py && python3 tests/test_hazards.py && python3 tests/test_dot511.py && python3 tests/test_parking.py && python3 tests/test_display_alerts.py && python3 tests/test_hos.py`

---

## Build Queue — Next Modules

Build one module at a time. Always ask before starting the next one.

| # | Module | Key Requirement |
|---|---|---|
| 1 | `core/hazards.py` | ✅ COMPLETE — 31 tests |
| 2 | `core/dot511.py` | ✅ COMPLETE — 41 tests |
| 3 | `core/parking.py` | ✅ COMPLETE — 39 tests |
| 4 | `core/hos.py` | ✅ COMPLETE — 49 tests |
| 5 | `core/feedback.py` | Driver report submission + upvote/dismiss |
| 6 | `core/savings.py` | Time + money saved tracker + shareable ASCII cards |
| 7 | `display/glance.py` | 2-second glance mode, max 6 lines, no scroll |
| 8 | `platforms/windows/main.py` | Windows terminal wrapper |
| 9 | `platforms/ios/main.py` | iOS iSH wrapper |
| 10 | cleanshothq.com | Coming soon landing page |

---

## SESSION 3 — Build Priorities

Start here next session. Build in this order. One module at a time, read CLAUDE.md first.

### 1. `core/feedback.py` — Driver Report Submission
- Submit feedback on road conditions, stops, hazards
- Upvote / dismiss other drivers' reports
- Claude AI parsing integration (`claude/parser.py`)
- Offline queue → backend sync stub (Phase 2)
- Subscription gated: solo_pro+
- Target: ~35 tests

### 2. `core/savings.py` — Time & Money Saved Tracker
- Calculate time saved vs. stopping for bad weather
- Calculate fuel/cost savings from route decisions
- Milestone celebrations (first save, 10th save, 100 hours saved, etc.)
- Shareable ASCII stats card (single-page, tweetable)
- Persisted in config dict under `savings_*` keys
- Target: ~25 tests

### 3. `display/glance.py` — 2-Second Glance Mode
- Max 6 lines, no scroll — driver glance only
- Ultra-compact for phones (36 chars)
- Shows: condition + temp, wind alert if any, HOS remaining, next stop distance
- `cleanshot glance` command
- Target: ~20 tests

### 4. `platforms/windows/main.py` — Windows Terminal Wrapper
- Windows CMD / PowerShell entry point
- SAPI TTS init check
- WinRT GPS availability check
- Pre-flight dep check (colorama, requests)
- Mirrors linux/main.py structure

### 5. `platforms/ios/main.py` — iOS iSH Wrapper
- iOS iSH shell entry point
- CoreLocation availability check
- AVSpeechSynthesizer TTS init check
- Mirrors linux/main.py structure

### 6. cleanshothq.com — Coming Soon Landing Page
- Simple static HTML/CSS — no framework
- Mobile-first, trucker-friendly design
- Email capture for early access
- Feature highlights: HOS, Parking Runway, TTS, Offline-first
- "Built for the road, not the boardroom" hero

---

## Voice Quality Standard — Non-Negotiable

Clean Shot uses natural human-sounding voices on all platforms.
**Robotic voices are never acceptable.** A trucker who hears a robotic voice turns TTS off.
A trucker who turns TTS off misses the black ice warning. Voice quality is safety.

| Platform | Approved Voice | Stars | Notes |
|---|---|---|---|
| Linux | Piper TTS — en_US-ryan-high | ⭐⭐⭐⭐⭐ | APPROVED ✓ |
| Linux fallback | Piper TTS — en_US-lessac-medium | ⭐⭐⭐⭐⭐ | If ryan unavailable |
| Linux fallback 2 | festival | ⭐⭐⭐ | If Piper not installed |
| Linux fallback 3 | pyttsx3/espeak en+m3 | ⭐⭐ | EMERGENCY ONLY — shows warning |
| Windows | SAPI — David or Mark | ⭐⭐⭐⭐ | Never use "Microsoft Sam" |
| macOS | say -v Samantha (or Alex) | ⭐⭐⭐⭐ | Never use bare `say` without -v |
| Android | termux-tts-speak -r 0.85 | ⭐⭐⭐ | Device Google TTS |
| iOS | AVSpeechSynthesizer en-US | ⭐⭐⭐⭐ | Natural system voice |

**When espeak/fallback is used:** always show:
`⚠️ Voice quality degraded — Run: cleanshot fix-voice`

**`cleanshot fix-voice`** auto-installs piper-tts + ryan-high model on Linux.

**Alert tones:** Distinct per-severity WAV tones play before every spoken alert.
Generated locally in pure Python. Stored in `~/.local/share/cleanshot/tones/`.
| Severity | Tone | Duration |
|---|---|---|
| INFO | Soft ascending C5→E5 | 0.3s |
| WARNING | Ascending A4→C5→E5 | 0.5s |
| CRITICAL | Descending A5→F5→D5 "BONG-BONG-BONG" | 0.8s |
| EMERGENCY | Rapid 880Hz pulse ×8 | 1.0s |

**Never regress to robotic voices. Never ship without a voice quality check in doctor.**

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
│   ├── hazards.py             ✅ COMPLETE — community reports + clustering, 31 tests
│   ├── dot511.py              ✅ COMPLETE — NWS backbone + 50-state framework, 41 tests
│   ├── parking.py             ✅ COMPLETE — runway + stops, 39 tests
│   ├── hos.py                 ✅ COMPLETE — FMCSA rules + advisory display, 49 tests
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
│   ├── display_alerts.py      ✅ COMPLETE — 5 levels + flash + ack + HOS, 40 tests
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

## Responsive Display System

All display modules are fully width-responsive (no hardcoded 80/50 column
widths). Every module reads `config["display_width_override"]` (int 20–300) or
falls back to `shutil.get_terminal_size()`. Minimum enforced: 36 columns.

4 display modes, all via local `_w(config)` / `_mode(w)` helpers:
- **ultra_compact** (`w < 40`): single-line per item, truncated to `w`
- **compact** (`w 40–60`): abbreviated, 1–2 lines per item
- **standard** (`w 60–80`): labeled rows, no descriptions
- **full** (`w 80+`): full detail, descriptions, notes

Files updated: `display/full.py`, `display/display_alerts.py`,
`core/hazards.py`, `core/dot511.py`, `core/parking.py`, `core/hos.py`,
`core/config.py` (added `display_width_override`), `core/weather.py`
(removed `min(..., 80)` cap on width).

Works on Android (Bold Blu K50, 36-char Termux), small tablets, and wide
desktop terminals.

---

## Session 4 Fixes — 2026-04-13

### What Was Fixed Tonight

**Version Files Created:**
- `clean-shot/VERSION` → 3.0.0
- `clean-shot/VERSION.dev` → 3.1.0-dev
- `clean-shot/CHANGELOG.md` → full v3.0 changelog

**Installer Fixes (all 5 platforms):**
- All 5 installers now launch Clean Shot immediately after install (no manual step)
- Linux: added Python 3.13+ warning + explicit python3.11 install attempt + dnf pre-update
- Linux: success screen no longer says "Open a new terminal" — just launches
- Android: removed "Restart Termux" instruction — launches in current session
- iOS: fixed launch for POSIX sh (replaced exec with safe command -v check)
- macOS/Windows: launch added (were missing entirely)

**Doctor Command (cmd_doctor) — full rewrite:**
Matches the v3.0 spec output format exactly.
Sections: SYSTEM / DEPENDENCIES / STORAGE / CONNECTIVITY / FEATURES / SUBSCRIPTION
- SYSTEM: platform, Python version (3.13+ gets "3.11 recommended"), Clean Shot version
- DEPENDENCIES: requests+version, colorama+version, pyttsx3 (Linux/Windows only)
- STORAGE: cache dir, config file, temp dir — all with fix commands on failure
- CONNECTIVITY: Internet, NOAA/NWS, Open-Meteo, Geocoding — 4 live checks, 5s timeout
- FEATURES: all 8 modules checked individually with operational/error status
- SUBSCRIPTION: plan, days remaining, upgrade link
- Summary: "ALL SYSTEMS OPERATIONAL" or "N issue(s) found — see above for fixes"
- Every failure shows exact fix command
- Support email at bottom

**First Run Setup (first_run_setup) — full rewrite:**
- New header: 🚛 WELCOME TO CLEAN SHOT v3.0
- 3 questions only: name (optional), location, vehicle type (5 options)
- Location: accepts City/State/ZIP or Enter for IP auto-detect
- Vehicle type: maps display names to internal wind-calc types
- Welcome screen: greeting, 30-day trial, CB radio welcome message
- TTS speaks welcome message on first launch (forced on for this one message)
- config["driver_name"] stored in config (new field added to _DEFAULTS)
- Never asks again (existing behavior — only runs when latitude is None)

**Error Messages (audit):**
- `resolve_location`: replaced ✗ error with friendly "Can't find that location" + examples
- `resolve_location`: "No location set" message now shows two example fix commands
- `get_weather_data`: replaced raw error with "Can't reach weather service" + "Check connection"
- linux/main.py: unhandled exception now shows "Something went wrong / support@cleanshothq.com"
- android/main.py: same friendly error wrapper

**Public README:**
Replaced detailed technical README with clean v3.0 marketing README:
- What's in v3.0 (feature list)
- One-line install per platform (all 5)
- Coming in v3.1 preview
- cleanshothq.com + support email
- "Built for the road, not the boardroom"
- No unbuilt features mentioned

### What Needs Real-Hardware Testing

| Platform | Test Focus |
|---|---|
| Android Termux | Install one-liner + auto-launch after install |
| iOS iSH | sh compatibility, slow git clone (~30s), launch |
| Windows 11 | winget Python/Git install, PowerShell profile, bat launcher |
| macOS M1/M2 | Homebrew ARM path, xcode-select wait loop |
| Linux (Fedora/Arch) | dnf/pacman install paths, python3.11 package name |

### Test Count: 277 / 277 passing

All 9 suites unchanged — new code (doctor, first_run) does not affect test modules.

---

## SESSION 4 — Build Priorities

Start here next session. Build in this order. One module at a time, read CLAUDE.md first.

### 1. `core/feedback.py` — Driver Report Submission
- Submit feedback on road conditions, stops, hazards
- Upvote / dismiss other drivers' reports
- Claude AI parsing integration (`claude/parser.py`)
- Offline queue → backend sync stub (Phase 2)
- Subscription gated: solo_pro+
- Target: ~35 tests

### 2. `core/savings.py` — Time & Money Saved Tracker
- Calculate time saved vs. stopping for bad weather
- Milestone celebrations
- Shareable ASCII stats card
- Target: ~25 tests

### 3. `display/glance.py` — 2-Second Glance Mode
- Max 6 lines, no scroll
- Ultra-compact for phones (36 chars)
- `cleanshot glance` command
- Target: ~20 tests

### 4. `platforms/windows/main.py` + `platforms/ios/main.py`
- Proper error handling, sys.path, dep checks (mirrors linux/main.py)

### 5. cleanshothq.com — Coming Soon Landing Page

---

*This file is auto-loaded by Claude Code in every session.*
*Update it when a module is completed or a key decision changes.*
*Last updated: 2026-04-13 — Session 4 complete. Doctor rewritten, first_run redesigned, 5 installers all launch-immediately, error messages humanized, version files created, public README updated. 277/277 tests passing.*

*Session 4 (continued) — Piper TTS integration: full neural voice on Linux. Cascade: piper→festival→pyttsx3. `cleanshot voices download`, `cleanshot voices download <name>`, `cleanshot settings voice <name>`. `test-tts` shows engine+voice+stars. Linux installer auto-installs piper-tts + en_US-lessac-medium model. 277/277 tests passing.*

*Session 4 (continued) — ryan-high approved + Alert Tone System + Repeat Prompt:*
*Default voice changed to en_US-ryan-high (approved, clearest quality). Alert tones: 4-severity WAV system (INFO chime / WARNING ascending / CRITICAL descending BONG / EMERGENCY rapid pulse), pure Python, no downloads. Repeat prompt (R to repeat / Enter / auto-timeout). Last-3-messages ring buffer for Hey Clean Shot repeat. EMERGENCY as 4th severity. Degraded voice warning when espeak is used. `cleanshot fix-voice` command. Doctor now has VOICE section. Windows SAPI prefers David/Mark. macOS say prefers Samantha. iOS AVSpeech prefers natural voices. `cleanshot settings tone on/off`, `tone-volume`, `repeat-timeout`, `voice ryan` (short alias). 357/357 tests passing (80 new tone/voice/repeat tests).*

*Session 5 — Android real-device fixes (Blu K50, Google Play Termux):*
*TTS fixed: Termux checked BEFORE Linux/piper (both show platform="linux"); subprocess.run not Popen; return False on failure stops fallthrough. Tones fixed: sox confirmed working on device; new platforms/android/tts_tones_android.py with INFO/WARNING/CRITICAL/EMERGENCY via play -n synth. GPS fixed: _get_termux_location() added to gps.py; fallback chain termux-location→IP geo→cached→ask; Google Play uses IP geo (termux-location unavailable). Installer: smart root install.sh dispatches to correct platform installer; SSL ca-certificates installed FIRST; F-Droid recommendation shown before install with Enter-to-continue; Google Play vs F-Droid auto-detected from TERMUX_VERSION. Doctor: Android section added. Product name updated: "Clean Shot — Driver Intelligence System" (CSDIS) in help/doctor/first-run/changelog/CLAUDE.md. 357/357 tests passing.*

## Android Platform Notes (Session 5 — confirmed on Blu K50)

**Google Play Termux limitations (TERMUX_VERSION contains "googleplay"):**
- `termux-location` NOT available → GPS falls back to IP geolocation
- Some Termux:API features missing
- Recommend F-Droid Termux for full functionality

**F-Droid Termux (recommended):**
- `termux-location -p gps -r once` → live GPS ✅
- Full Termux:API feature set
- Latest updates

**Detection:** `"googleplay" in os.environ.get("TERMUX_VERSION", "").lower()`

**Android TTS:** `subprocess.run(["termux-tts-speak", text], timeout=30)` — confirmed working.
**Android tones:** `play -n synth <dur> sine <freq>` via sox — confirmed working.
**Android GPS:** termux-location (F-Droid) → IP geolocation (Google Play) → cached → ask.
**SSL fix:** `pkg install -y ca-certificates openssl-tool` must be FIRST step in installer.
