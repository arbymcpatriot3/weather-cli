# Clean Shot
[![Version](https://img.shields.io/badge/version-3.0.0-blue)](https://github.com/arbymcpatriot3/weather-cli/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Built for the road, not the boardroom.**

Clean Shot is a terminal weather and road intelligence platform for truck drivers.
Full-featured on a phone screen. Fast on 2G. Advisory HOS tracking, DOT/511 alerts,
community hazard reports, smart parking runway, and text-to-speech — all offline-first,
no API key required.

---

## What It Does

| Feature | Tier | Description |
|---|---|---|
| Current weather + forecast | Free | Temp, wind, rain, hourly, 7-day |
| Road hazard detectors | Free | Black ice, fog, flood, diesel gel, high wind |
| NOAA weather alerts | Free | Active NWS alerts for your location |
| HOS Guardian | Solo Pro+ | Advisory 11h/14h/30-min break tracking |
| DOT/511 Advisories | Solo Pro+ | Chain laws, closures, weather advisories |
| Smart Parking Runway | Solo Pro+ | Miles left before you must stop |
| Community Hazards | Solo Pro+ | Driver-reported road conditions |
| Text-to-Speech | Solo Pro+ | CB radio voice alerts while driving |
| GPS integration | Solo Pro+ | Live position, auto-detect highway |

---

## Works on Every Screen

Clean Shot adapts to any terminal width automatically:

- **36 chars** — Android phone (Termux), single-line ultra-compact mode
- **40–60 chars** — Small tablets, abbreviated compact mode
- **60–80 chars** — Standard terminal
- **80+ chars** — Desktop/wide, full detail mode

Set a fixed width override: `cleanshot settings width 38`

---

## Quick Start

### Linux / Android (Termux)

```bash
curl -fsSL https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/clean-shot/platforms/linux/install.sh | bash
```

Then run:

```bash
cleanshot
```

### Manual

```bash
git clone https://github.com/arbymcpatriot3/weather-cli.git
cd weather-cli/clean-shot
pip install -r requirements.txt
python3 platforms/linux/main.py
```

---

## Commands

```
cleanshot                        Full report — weather + road intel + HOS
cleanshot alerts                 Active weather alerts only
cleanshot route "Start" "End"    Weather along a route (5 stops)
cleanshot map                    Regional weather overview
cleanshot watch                  Auto-refresh every 15 minutes
cleanshot json                   Raw JSON output
cleanshot settings               View/update settings
cleanshot settings height 13.5   Set vehicle height (feet)
cleanshot settings wind 35       Set wind alert threshold (mph)
cleanshot settings tts on        Enable text-to-speech alerts
cleanshot settings 24h           Switch to 24-hour time
cleanshot settings location      Change default location
cleanshot help                   Full command reference
```

---

## Road Intelligence (Solo Pro+)

**HOS Guardian** — Advisory hours-of-service tracking. Not an ELD. Tracks your
11-hour drive limit, 14-hour duty window, and 30-minute break requirement.
Announces via TTS when you're 2h, 1h, 30min, and 15min from your limit.

**Smart Parking Runway** — Calculates how many miles you can legally drive before
HOS forces a stop. Shows the nearest truck stops (Pilot, Love's, Flying J, TA/Petro)
within your runway. Embedded database of ~80 stops on major corridors; Overpass API
for live results when connected.

**DOT/511 Advisories** — NWS-backed road condition feed covering all 50 states.
Chain requirements, winter advisories, closures, high wind. No API key.

**Community Hazards** — Submit and receive driver-reported road conditions.
Black ice, fog, accidents, construction, debris. Clustered by proximity.
Under 200 bytes per report — built for 2G.

**Text-to-Speech** — CB radio voice alerts dispatched while driving.
Quiet hours, repeat suppression, speed-aware queueing.
Supports Termux, Linux (pyttsx3), Windows (SAPI), iOS/macOS (AVSpeechSynthesizer).

---

## 7 Offline Hazard Detectors

No network call needed. Runs against cached Open-Meteo data.

| Detector | Trigger |
|---|---|
| Black ice | 20–34°F + precipitation ≥ 20% |
| Bridge freeze | Temp ≤ 38°F |
| Fog | Weather code 45/48 |
| Flood | Heavy rain codes + 6h sustained ≥ 60% |
| Diesel gel | Current or next 6h below threshold |
| High wind | Gusts vs threshold × vehicle-type factor |
| Mudslide | ≥ 80% precip for 3 consecutive hours |

---

## Subscription Tiers

| Tier | Price | Who It's For |
|---|---|---|
| Free | $0 | Basic weather + NOAA alerts |
| Solo Pro | $19.99/mo | Independent drivers — all features |
| Pro Plus | $29.99/mo | Fleet view + API access |
| Fleet | $15/seat/mo | Dispatch dashboard |
| Enterprise | Custom | White-label |

**Referral program:** 10% off per referral. Free forever at 10 referrals.
We pay you monthly at 11+.

---

## Requirements

- Python 3.8+
- `requests`, `colorama` (installed by install.sh)
- Optional: `pyttsx3` (Linux TTS)

No API keys. No account needed to get started.

---

## Data Sources

| Source | Used For |
|---|---|
| [Open-Meteo](https://open-meteo.com/) | Weather forecasts worldwide |
| [NOAA / NWS](https://www.weather.gov/) | US weather alerts + DOT advisories |
| [OpenStreetMap Overpass](https://overpass-api.de/) | Truck stop locations |
| [Nominatim](https://nominatim.org/) | Reverse geocoding |
| [ipapi.co](https://ipapi.co/) | IP-based location (auto-detect only) |

All free. No registration required.

---

## Architecture

```
Offline-first       Cache → network, never the reverse
2G / EDGE capable   Full route refresh < 50 KB
Battery-friendly    < 3% drain per hour, no background polling
Fast cold start     < 2 seconds
Truckers first      Every feature decision goes through this filter
```

---

## Author

**Arby McPatriot** — Blue Collar Nation LLC
GitHub: [arbymcpatriot3](https://github.com/arbymcpatriot3)

---

## License

MIT License — free to use, modify, and distribute.
