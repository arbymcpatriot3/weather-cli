# Weather CLI
[![GitHub downloads](https://img.shields.io/github/downloads/arbymcpatriot3/weather-cli/total)](https://github.com/arbymcpatriot3/weather-cli/releases)
[![Version](https://img.shields.io/badge/version-2.0.0-blue)](https://github.com/arbymcpatriot3/weather-cli/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A fast, lightweight terminal weather tool built for truckers, travelers, and
anyone who needs accurate weather and road conditions without a heavy app.

Runs entirely in the terminal. No account needed. No API key required.
Works great on old hardware, servers, Raspberry Pi, and SSH sessions.

---

## Features

- Current conditions — temperature, feels-like, humidity, wind, sunrise/sunset
- 24-hour hourly forecast with temperature bars and gust warnings
- 7-day forecast with rain probability and wind alerts
- Rain probability timeline for the next 12 hours
- Active weather alerts via NOAA / National Weather Service (US)
- Trucker wind alerts — flags dangerous gusts for high-profile vehicles
- Route weather planner — weather at 5 stops along any route
- Regional weather map — overview of nearby cities
- Auto-detects your location on first run
- Per-location caching — 10 minute refresh, works offline with stale data
- Color-coded output — temperatures, wind speed, rain chance
- Watch mode — auto-refreshes every 15 minutes
- JSON output for scripting and automation
- 80-column display — works on any terminal width
- Compact mode for small screens

---

## Requirements

- Python 3.8 or newer
- `pip` (Python package manager)

Dependencies (installed automatically):
- `requests`
- `colorama`

---

## Installation

### One-line install (Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/install.sh | bash
```

### Manual install

```bash
git clone https://github.com/arbymcpatriot3/weather-cli.git
cd weather-cli
pip install -r requirements.txt
python3 weather.py
```

On first run, the setup wizard will ask for your location and preferences.

### Make it a system command (optional)

```bash
sudo cp weather.py /usr/local/bin/weather
sudo chmod +x /usr/local/bin/weather
```

Then just type `weather` from anywhere.

---

## Usage

```
weather                              Full weather report (default location)
weather "Chicago IL"                 Weather for a specific city
weather --location "08079"           Weather by ZIP code
weather --location "39.71,-75.52"    Weather by coordinates
weather simple                       One-line summary
weather compact                      80-column compact view
weather watch                        Auto-refresh every 15 minutes
weather json                         Raw JSON output for scripting
weather alerts                       Active weather alerts only
weather map                          Regional weather overview
weather route "Start" "End"          Weather along a route (5 stops)
weather settings                     View current settings
weather settings 24h                 Switch to 24-hour time format
weather settings height 13.5         Save vehicle height for wind alerts
weather settings wind 35             Set wind alert threshold (mph)
weather settings location            Change default location
weather help                         Show help
weather --fresh                      Force fresh data (skip cache)
```

---

## Example Output

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Weather for Pennsville, New Jersey  v2.0.0                                  │
└──────────────────────────────────────────────────────────────────────────────┘

Location: Pennsville, New Jersey
Updated:  04/04/2026 12:33 PM

Current Conditions
--------------------------------------------------------------------------------
Temperature     : 80.5°F  (feels like 88.7°F)
Condition       : Clear sky ☀
Humidity        : 63%
Wind            : 2.7 mph  S ↓
Sunrise / Sunset: 06:40  /  19:28

Hourly Forecast (Next 24 hours)
--------------------------------------------------------------------------------
12:00 AM EDT |  61.5°F | #####                | Gust: 11.9
 1:00 AM EDT |  61.6°F | #####                | Gust: 12.8
...
 2:00 PM EDT |  83.8°F | #################### | Gust:  6.7

7-Day Forecast
--------------------------------------------------------------------------------
Sat Apr 04  Overcast ☁
     High 84°F   Low 53°F   Rain 10%

Sun Apr 05  Heavy rain 🌧
     High 74°F   Low 45°F   Rain 84%
     ⚠ Gusts up to 38 mph
```

---

## Trucker Features

Weather CLI was designed with truckers in mind:

**Wind alerts** — configurable gust threshold (default 40 mph). Any hour
with gusts above the threshold is flagged in the hourly view and a full
alert banner is shown at the top of the report.

**Route planner** — check weather at 5 evenly spaced points along any
route. Great for planning a long haul and knowing what you'll drive into.

```bash
weather route "Pennsville NJ" "Chicago IL"
```

**Vehicle height** — save your rig's height and get relevant warnings:

```bash
weather settings height 13.5
```

**Low bandwidth** — minimal data usage. Caches results for 10 minutes.
Designed to work on cellular data plans without burning through your data.

---

## Designed For

- Truckers and long-haul drivers
- Linux servers and SSH terminals
- Older computers and Raspberry Pi
- Minimal and headless environments
- Anyone who prefers the terminal

---

## Data Sources

All data sources are free with no API key required:

- [Open-Meteo](https://open-meteo.com/) — weather forecasts worldwide
- [NOAA / National Weather Service](https://www.weather.gov/) — US alerts
- [ipapi.co](https://ipapi.co/) — IP-based location (auto-detect only)

---

## Coming Soon

- Windows CMD / PowerShell version
- iOS console version
- Android app (free trial)
- iOS app (free trial)

---

## Author

**Arby McPatriot**
GitHub: [arbymcpatriot3](https://github.com/arbymcpatriot3)

---

## License

MIT License — free to use, modify, and distribute.
