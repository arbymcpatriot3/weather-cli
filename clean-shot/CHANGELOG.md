# Clean Shot — Driver Intelligence System — Changelog
# By Blue Collar Nation LLC | cleanshothq.com

## v3.0.0 — April 2026
### The Road Intelligence Edition

First stable release.

### Features
- Weather + 7 road alert detectors
  (black ice, bridge freeze, fog, flood, diesel gel, high wind, mudslide)
- Community hazard reports with GPS geo-confirmation
- DOT/511 feeds all 50 states
- Smart parking runway (HOS-aware)
- HOS guardian (FMCSA 11/14/70 hour rules)
- Text-to-speech voice alerts (CB-style, 5 platform dispatch)
- Flash + beep critical alerts (5 severity levels)
- GPS navigation math
- Multilingual foundation (English + Spanish)
- Referral engine
- Auto-updates
- Error telemetry
- One-line install: Linux, Windows, macOS, Android Termux, iOS iSH

### Platforms
- Linux Mint 22+ / Ubuntu 20.04–24.04 / Debian 11–12 / Fedora 38–40 / Arch
- Windows 11
- macOS (M1/M2/M3/M4 + Intel)
- Android (Termux — F-Droid recommended)
- iOS (iSH)

---

## v3.1.0-dev — Android Fixes (2026-04-14)

### Android — real-device testing on Blu K50

**TTS fixed:**
- `termux-tts-speak` checked BEFORE Linux/piper path — both show `platform="linux"`
- Changed from `Popen` to `subprocess.run` — confirmed working
- `return False` on failure stops fallthrough to Linux engine (which doesn't exist on Android)

**Alert tones fixed:**
- sox confirmed working: `play -n synth 0.3 sine 523`
- New `platforms/android/tts_tones_android.py` — INFO/WARNING/CRITICAL/EMERGENCY via sox
- Added `pkg install -y sox` to Android installer

**GPS fixed:**
- Added `termux-location` support in `core/gps.py` (F-Droid Termux only)
- GPS fallback chain: termux-location → IP geolocation → cached → ask user
- Google Play Termux uses IP geolocation (termux-location unavailable on Google Play)
- Shows GPS source: `GPS ✅` or `IP geolocation ⚠️` or `Cached ⚠️`

**Installer:**
- Smart root `install.sh` — detects Android/macOS/Linux, runs correct installer
- SSL certificates installed FIRST (fixes curl/git failures on fresh Termux)
- F-Droid recommendation shown before install begins, with Enter-to-continue pause
- Google Play vs F-Droid auto-detected from `TERMUX_VERSION`

**Doctor:**
- Android section added: termux-api check, Google Play vs F-Droid detection, sox check

**Product name:**
- Full name: "Clean Shot — Driver Intelligence System" (CSDIS)
- Updated in: help, doctor, first-run setup, TTS test, changelog, installers
