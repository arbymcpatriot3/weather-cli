# Clean Shot — Driver Intelligence System — Changelog
# By Blue Collar Nation LLC | cleanshothq.com

## v3.0.3 — April 2026 (real-world testing fixes)

### iOS iPhone SE Gen 3 + Android Blu K50 — field test fixes

**Trial features fully unlocked:**
- All features now available during 30-day trial, no exceptions
- Trial now returns `True` for ALL features (was limited to solo_pro tier only)
- Fleet, Pro Plus, and Enterprise features also unlocked during trial

**Auto voice setup on install:**
- Voice system configured automatically — user never sees "Run cleanshot fix-voice"
- Android: piper-tts attempted on aarch64; falls back to termux-tts-speak
- iOS iSH: espeak-ng en+m3 at rate 130 (best available on x86 Alpine)
- Linux: `fix_voice()` runs silently at end of install before doctor
- Native iOS app (Phase 2) will have full AVSpeech natural voice

**Hourly forecast starts at current hour:**
- Fixed datetime comparison to use Python datetime objects (was string comparison)
- More reliable across all timezones and platforms

**Android TTS timeout reduced:**
- `termux-tts-speak` timeout reduced from 30s to 5s — never blocks app
- Silently continues if TTS fails; no error spam

**piper-tts install fix:**
- All installers now use `--break-system-packages` flag (required on PEP 668 systems)
- iOS iSH: gracefully handles missing x86 wheels; falls back to espeak-ng
- Android aarch64: attempts piper-tts + ryan-high download; falls back to device TTS

**Internet connectivity check fixed:**
- Doctor now checks Open-Meteo as primary internet test (was api.weather.gov)
- Open-Meteo is always reachable; NWS checked separately (US-only service)
- No more false "❌ no connection" when APIs are actually reachable

---

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
