# Clean Shot — Driver Intelligence System — Changelog
# By Blue Collar Nation LLC | cleanshothq.com

## v3.0.12 — May 2026

### Stripe Checkout & Referral System (Cloudflare Backend)

**Stripe subscriptions wired up — checkout creates real billing sessions:**
- `POST /v1/checkout` — validates `price_id` against 7 known Stripe price IDs,
  creates a Stripe Checkout Session with 30-day trial, returns `checkout_url`
- Referral code accepted at checkout (`ref_code`): referrer's active subscription
  confirmed before marking the referral `pending` — prevents code reuse during checkout

**Referral code generation and stats:**
- `POST /v1/referral/generate` — Bearer auth; returns existing code or generates
  a unique `{name}-{4chars}` code (e.g. `bruce-4x7k`), stored in D1
- `GET /v1/referral/status` — returns `ref_code`, `referral_url`, `active_referrals`,
  and `monthly_discount` for authenticated subscriber

**Stripe webhook handler (`POST /v1/webhooks/stripe`):**
- HMAC-SHA256 signature verified via `crypto.subtle` (Workers-native, 5-min replay protection)
- `subscription.created` → marks referral `used`, credits referrer +$1.00/mo coupon via Stripe
- `subscription.updated` → syncs status to D1
- `subscription.deleted` → marks subscription `canceled`, removes referrer's discount credit
- Discount model: $1.00/mo per active referee, max $5.00/mo (5 referrals)
- Deterministic coupon IDs (`ref-disc-100` … `ref-disc-500`) — idempotent, reused across referrers

**D1 schema additions (`cloudflare/migrations/001_referrals.sql`):**
- `referrals` table — one row per referral code; lifecycle: `active → pending → used`
- `referral_discounts` table — tracks each referrer's cumulative discount and coupon
- 3 indexes: `ref_code`, `referrer_email`, `referee_stripe_id`

**Security fixes:**
- `isAdminAuthorized()` now reads `env.ADMIN_KEY` (was using a module-level hardcoded constant)
- CORS headers updated to include `Authorization` for Bearer-auth endpoints
- No Stripe keys in code — `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` are Wrangler secrets

**Deployment:** `wrangler secret put STRIPE_SECRET_KEY`, `wrangler secret put STRIPE_WEBHOOK_SECRET`,
configure webhook at Stripe Dashboard → Developers → Webhooks → `api.cleanshothq.com/v1/webhooks/stripe`

---

## v3.0.11 — May 2026

### Road Intelligence & Security

**road511 API key security hardened — key no longer ships in binary:**
- Hardcoded `road511_api_key` removed from `_DEFAULTS` in `core/config.py`
- Key resolution order: `R511_API_KEY` env var → `~/.config/cleanshot.credentials`
  JSON file → `config["road511_api_key"]` (set via `cleanshot settings road511-key`)
- Fallback: Cloudflare Worker proxy at `api.cleanshothq.com/v1/road511/*` —
  validates CleanShot license server-side, road511 key stays on the server

**Cloudflare Worker: road511 proxy endpoint added (`/v1/road511/*`):**
- CleanShot app calls the CF proxy instead of road511 directly when no local key exists
- Worker validates `license_key` + `machine_id` against D1 (blocks expired trials, blocked machines)
- Proxies GET to `api.road511.com/api/v1/*` with server-side `R511_API_KEY` secret
- Deploy: `wrangler secret put R511_API_KEY` then `wrangler deploy`

**core/road511.py — proxy fallback wired into all fetch functions:**
- `fetch_events()`, `fetch_bridges()`, `fetch_weigh_stations()`,
  `fetch_truck_parking()`, `fetch_cameras()` all try direct key first,
  then proxy automatically — zero config change for users
- `check_route_safety()` returns `{"available": False}` only when both
  direct key AND local license are absent (true offline/unregistered state)

**Legacy root-level v2 stubs moved to `legacy/`:**
- `api.py`, `weather.py`, `config.py`, `display.py`, `parse.py`
  moved from repo root to `legacy/` — not shipped to users, not imported by any active code

**Version:** 3.0.10 (platform parity) → **3.0.11** (road intelligence security)

---

## v3.0.10 — May 2026

### Platform Parity

**All platforms now match Windows v3.0.10 feature level.**

**Linux/macOS entry point fixed:**
- `_REPO_ROOT` variable renamed to `_CLEAN_SHOT_DIR` — correct name for correct path
- Dead path (`clean-shot/clean-shot/`) removed from `sys.path`
- `_ensure_console_size()` added — grows terminal to 120×50 on launch
  - Tries ANSI xterm resize sequence first (`ESC[8;50;120t`)
  - Falls back to `stty` to set the kernel TTY record
  - No-ops on Android/iOS (Termux/iSH control window size through the app)
- Added `if __name__ == "__main__"` guard
- macOS confirmed: uses Linux entry point (install.sh routes to `platforms/linux/main.py`)

**Android entry point fixed:**
- `_REPO_ROOT` variable renamed to `_CLEAN_SHOT_DIR` (same path bug as Linux)
- Added `_KNOWN_COMMANDS` routing guard — prevents city names like "parking" or
  "doctor" from being mistakenly routed as commands instead of location lookups

**iOS entry point rewritten (was a 17-line stub):**
- Added TMPDIR setup (`/tmp` fallback for iSH)
- Added pre-flight dependency check (colorama, requests)
- Added `_KNOWN_COMMANDS` routing guard
- Added full error handling with `CLEANSHOT_DEBUG` support
- Correct path setup matching Linux/Android structure
- Proper `if __name__ == "__main__"` guard

**`weather-cli` repo references fully purged:**
- All 5 platform install scripts: `github.com/arbymcpatriot3/CleanShot` ✅ (done in v3.0.9)
- `cleanshot.sh` (root dispatcher): macOS branch fixed
  (`./weather-cli/clean-shot/...` → `./clean-shot/...`)
- `worker.js`: GitHub links updated
- `index.html`: 5 GitHub download links updated
- `build/build_installer.ps1`: comments and error message updated
- `build/cleanshot.spec`: comments updated
- `install.sh` (root): repo URL updated
- Active Python source: clean (`grep -r "weather-cli" clean-shot/*.py` → 0 hits)
- Remaining: only CHANGELOG historical notes + root-level legacy v2 stubs (not shipped)

---

## v3.0.9 — May 2026

### Build & Distribution

**Version detection fixed:**
- App no longer reports v0.0.0 when checking for updates
- `_local_version()` now reads from `core.config.VERSION` (always correct), with VERSION file as fallback
- Works correctly in both dev and PyInstaller bundle modes

**Window size fixed:**
- App now launches at 120×50 console size (no more scrolling required)
- Windows BAT launcher sets `mode con: cols=120 lines=50` before starting
- Interactive (double-click) launch also resizes via `_ensure_console_size()`

**Install script URLs corrected:**
- All 5 install scripts now point to `github.com/arbymcpatriot3/CleanShot` (was `weather-cli`)
- Linux: `INSTALL_DIR` corrected from `~/weather-cli` to `~/CleanShot`

**PyInstaller build fixed:**
- GitHub Actions workflow now uses `cleanshot.spec` (was `api.py` — wrong entry point)
- Spec file now uses `SPECPATH` for all paths — no more hardcoded `D:\weather-cli\` references
- Workflow installs `pywin32` and `pyttsx3` (required for Windows build)
- Workflow uses `clean-shot/requirements.txt` (not root-level)
- Signed exe artifact renamed `cleanshot.exe` (matches spec output)

**Referral tracking added:**
- First launch checks for `--ref=CODE` flag or `install.ref` file
- Referral code saved to config and passed to license API on registration
- Enables creator referral program (TikTok/affiliate links)

---

## v3.0.6 — April 2026

### Installer improvements

**Windows installer rewritten:**
- Fully hands-free — auto-installs Python 3.11 + Git via winget
- Blocks Python 3.14 (known WinError 123 crash on Windows)
- Creates cleanshot.bat + PowerShell profile function
- Launches Clean Shot automatically after install

**All 5 installers launch Clean Shot immediately after install:**
- No manual step required after install completes
- Linux: success screen no longer says "Open a new terminal"
- Android: launches in current Termux session (no restart needed)
- iOS: sh-compatible launch (no bash-isms)
- macOS: both Apple Silicon and Intel PATH handling

**InnoSetup installer (CleanShotSetup.exe):**
- Windows GUI installer added for non-technical users
- No admin required — installs to `%LocalAppData%\Programs\Clean Shot`
- Creates desktop shortcut and adds to PATH (optional)
- Launches Clean Shot after install

---

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
