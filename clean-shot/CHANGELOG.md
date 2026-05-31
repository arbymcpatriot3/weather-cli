# Clean Shot — Driver Intelligence System — Changelog
# By Blue Collar Nation LLC | cleanshothq.com

## v3.0.15 — May 2026

### Flyer route fix, truck icon restored, D1 migrations applied, worker deployed

**Critical fix — `/flyer` now serves the PDF correctly:**
- `_redirects` file created at repo root (Cloudflare Pages standard)
- `cleanshothq.com/flyer` → `api.cleanshothq.com/flyer` (302)
- `cleanshothq.com/download/*` → `api.cleanshothq.com/download/:splat` (302)
- `cleanshothq.com/favicon.ico` → `api.cleanshothq.com/favicon.ico` (302)
- Worker `/flyer` Cache-Control bumped to `max-age=86400` (24h)
- Filename corrected: `CleanShotHQ_Flyer.pdf` in Content-Disposition

**App icon fix — truck icon restored:**
- `assets/cleanshot.ico.old` (15,960 bytes, original truck icon) restored as `cleanshot.ico` and `favicon.ico`
- Previous 216-byte broken icon replaced
- Correct icon uploaded to R2 remote: `favicon.ico`, `CleanShotHQ_Flyer_v9.pdf`

**D1 remote database — migrations applied:**
- Migration 001 (referrals, referral_discounts) — applied remotely
- Migration 003 (hazard_log, session_log, rate_limits) — applied remotely
- All 11 tables now live in remote D1

**Worker deployed** — version 753553be, bindings confirmed (DB + RELEASES)

**Session 7 items confirmed complete (no code changes needed):**
- Welcome email via MailChannels on `subscription.created` webhook ✓
- `POST /v1/account/recover` — forgot license key → email ✓
- Recovery UI in dashboard.html with "Forgot your key?" link ✓
- "Getting a new device?" message in dashboard login ✓
- `POST /v1/account/resend-welcome` — Stripe last4 verification ✓

---

## v3.0.14 — May 2026

### Privacy Policy, Terms of Service, CRLF Fix, Legal Pages

**CRLF fix — all shell scripts converted to LF-only:**
- All 9 `.sh` files in `platforms/` and repo root fixed (were breaking on Android/Linux)
- `.gitattributes` added to repo root — prevents future CRLF contamination
- Shell scripts, Python, JS, TOML, SQL, HTML, CSS, YAML all enforced as LF
- Binary files (ico, png, pdf, exe) marked as binary (never touched by git)

**Legal pages — Privacy Policy, Terms of Service, Verification:**
- `privacy.html` already in repo — wired up with footer links across all pages
- `terms.html` created — full ToS covering safety disclaimer, HOS advisory,
  billing terms, license grant, acceptable use, IP, liability, NJ governing law
- `verify.html` created — company verification page for Microsoft SmartScreen,
  Apple App Store, Google Play, and Windows Store reviews
- All three accessible at `cleanshothq.com/privacy`, `/terms`, `/verify` via Cloudflare Pages
- Routes added to `cloudflare/worker.js` for `api.cleanshothq.com` domain

**Privacy + Terms links in all page footers:**
- `index.html`, `privacy.html`, `terms.html`, `verify.html`, `dashboard.html`, `subscribe.html`

**`subscribe.html` fine print updated:**
- HOS Guardian advisory disclaimer added: "HOS Guardian is an advisory tool only
  and is not a certified ELD device under FMCSA regulations."
- Terms of Service and Privacy Policy links already active (no change needed)

**Microsoft SmartScreen submission prep:**
- `verify.html` at `cleanshothq.com/verify` provides company + signing info
- Submit to SmartScreen: Privacy = `cleanshothq.com/privacy`, Verify = `cleanshothq.com/verify`

---

## v3.0.13 — May 2026

### App Icon, Flyer Viewer, GPS-Speed-Aware Refresh, Website Flyer

**App icon integrated throughout:**
- `cleanshot.ico` bundled inside exe via PyInstaller `datas` + `icon=` parameter
- Console window title-bar icon set via `WM_SETICON` + `LoadImageW` at launch
- `CleanShotSetup.iss` updated to version 3.0.13; `.ico` installed alongside exe for shortcut icons
- `favicon.ico` at repo root; served from `cleanshothq.com/favicon.ico` via R2

**Flyer viewer (`[F]` from main menu):**
- Opens `CleanShotHQ_Flyer_v9.pdf` in default PDF viewer via `os.startfile()`
- Finds file in PyInstaller bundle (`sys._MEIPASS`), exe directory, or dev assets path
- PDF bundled into exe via `cleanshot.spec` datas
- `cleanshothq.com/flyer` serves the PDF inline from R2

**GPS-speed-aware continuous refresh:**
- `get_gps_speed_mph()` — tries Windows WinRT Location API, then gpsd fallback
- `smart_refresh_interval()` — parked=20min, city=8min, highway approach=4min, highway=2min
- `[A]` in continuous monitor toggles GPS-auto mode; header shows "🚗 45 mph → 4 min refresh"
- `+`/`-` keys switch to manual mode; `A` toggles back to GPS-auto

**Website:**
- `cleanshothq.com/flyer` — PDF served inline from R2 (Content-Disposition: inline)
- Flyer link added to footer and contact section of `index.html`
- `cloudflare/wrangler.toml` — custom domain route added (removes deploy warning)

---

### Full-Window Launch, Continuous Monitor, Icon Glossary

**Windows: app now launches maximized (`SW_MAXIMIZE`):**
- Console window maximized via `ctypes.windll.user32.ShowWindow(hwnd, 3)` on startup
- Console title set: "CleanShot HQ v3.0.13 — Road Intelligence"
- Buffer grows to 180×50 as fallback

**Continuous monitoring mode (`[C]` from main menu):**
- Auto-refreshes the full dashboard every 1/2/5/10/15/30 minutes
- Non-blocking keyboard: Q=quit, R=refresh now, +/- to adjust interval
- TTS speaks new critical/high hazards (compares hashes cycle-to-cycle)
- New hazards logged to Worker via `hazard_logger.log_hazard()` automatically
- Session logged to Worker on exit via `hazard_logger.log_session()`
- Linux/macOS/Android: text-only continuous mode via `cleanshot monitor [minutes]`

**Icon & symbol glossary (`[?]` from main menu):**
- All hazard icons, severity levels, status symbols, truck stop amenities, HOS indicators
- Paginated by section — press Enter to continue, Q to return to menu
- `core/glossary.py` — `GLOSSARY` dict + `show_glossary()` function

**Referral reminder on startup:**
- One-line reminder shown once per session if referral_count < 5
- Includes shareable URL (uses saved ref code if available)
- Never shown when max $5/mo discount is already active

**New modules:**
- `core/glossary.py` — icon/symbol reference
- `core/ui.py` — platform detection helpers (`is_mobile`, `clear_screen`, `supports_tts`, etc.)
- `platforms/README.md` — platform support matrix and native app roadmap

---

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
