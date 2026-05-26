# CleanShot — Next Session Backlog
## Saved after v3.0.9 release — May 25, 2026

---

## 🔴 Do First (Before Truckers Ask)

### 1. Icon & Symbol Glossary
**Why:** Truckers shouldn't have to guess what ⚖️ or [C] means.
The app should be self-explanatory.

Add `cleanshot help icons` command:

```
Display icons:
⛽  Diesel fuel available
🚿  Shower facilities
🍔  Restaurant / food
📶  WiFi available
⚖️  Weigh station
👕  Laundry available
🌡  Temperature
💨  Wind speed / direction
🌧  Rain probability
📍  Current location
✅  Clear / safe
🚨  Hazard detected
⚠️  Warning / unknown status
✓   All clear (no issues)
[C] Chain control required
[X] Road closure
[B] Bridge restriction
[W] Weight restriction
[!] Weather advisory / incident
[-] Low priority item

Severity colors:
RED    Critical or major hazard
YELLOW Warning or unknown status
GREEN  Clear or informational
WHITE  Low priority
```

Also:
- Add glossary to bottom of `cleanshot help` output
- Print once during first_run_setup()
- Add to GitHub README for dispatchers and fleet managers
- Add Spanish translations for all labels when language = "es"

---

### 2. Road511 API Key — Verify Working
After rotating the key, the 401 error appeared on first run.
The fix is: `cleanshot settings road511-key <new_key>`
But this should be caught more gracefully at startup with a
clear message instead of a raw 401 error in stderr.

**Add to startup check in road511.py:**
```python
# On 401, give a helpful message not a raw error
if r.status_code == 401:
    print("⚠  Road511 API key rejected (401). Run:", file=sys.stderr)
    print("   cleanshot settings road511-key <your-key>", file=sys.stderr)
    return []
```

---

### 3. Windows Installer (Inno Setup)
Currently CleanShot ships as a raw .exe — professional but not polished.
Inno Setup wraps it into a proper setup wizard with:
- Start Menu shortcut
- Uninstall entry in Control Panel
- PATH set automatically (no manual env var needed)
- Version shown in Windows Apps list

Tools needed (both free):
- PyInstaller (already using) → cleanshot.exe
- Inno Setup → CleanShotSetup.exe
  Download: jrsoftware.org/isinfo.php

For enterprise/fleet customers later:
- Advanced Installer (advancedinstaller.com) — paid
  Adds code signing, MSI packaging, auto-update, IT-friendly deploy

---

## 🟡 Next Feature Sprints

### v3.1.0 — Community Hazard Reports
`core/feedback.py` stubs are ready. Full spec already written.
Needs CleanShot backend endpoints first:
```
POST /api/v1/hazards         Submit a report
GET  /api/v1/hazards/feed    Receive nearby reports
POST /api/v1/hazards/<id>/upvote
POST /api/v1/hazards/<id>/dismiss
```
Features:
- `cleanshot report black_ice` — quick submit
- `cleanshot report` — interactive menu
- `cleanshot feed` — show nearby driver reports
- Compressed payload < 200 bytes for 2G upload
- Free to submit, Solo Pro+ to receive
- Spanish labels when language = "es"

---

### v3.1.1 — Multi-Model Code Review Pipeline
Safety-critical functions reviewed by multiple AI models before commit.
Prevents the kind of issues we caught manually (0.5 ft margin, safe=True default).

Workflow:
```
Claude Code writes → qwen3-coder:30b reviews → deepseek-r1:14b
reasons through safety logic → feedback to Claude Code → tests → commit
```

Ollama models on Bruce's Linux machine:
- qwen3-coder:30b  — line-by-line code review
- deepseek-r1:14b  — safety logic reasoning
- glm-4-flash      — fast sanity checks

Script location: tools/review_pipeline.sh
Trigger on: any function touching bridge clearance, weight limits,
            safety flags, or route data

---

### v3.2.0 — Android App
Key decisions to make in planning session:
- Native Android (Kotlin) vs React Native vs PWA?
- CLI logic in Python stays as backend/library
- UI needs: big buttons, voice-first, dash-mount friendly
- Same feature parity as Windows where possible
- Road511, weather, parking, HOS all need to work
- Offline mode critical — truckers lose signal

---

### v3.2.1 — iOS App
Same planning session as Android.
Key difference: Apple App Store review process is stricter.
TTS uses AVSpeechSynthesizer (built-in, no extra install).
"Hey Clean Shot" wake word needs iOS background audio permission.

---

### v3.2.2 — macOS + Linux CLI Parity
CleanShot already runs on both — but:
- macOS: TTS uses `say` command (already supported)
- Linux: TTS uses espeak/festival/piper (already supported)
- Both need: same PATH setup, same first_run_setup experience
- Package managers: Homebrew formula (macOS), apt/snap (Linux)
- Test suite should run clean on all platforms

---

## 🔵 Longer Term

### Inno Setup Professional Installer
When ready for wide customer release:
1. PyInstaller → cleanshot.exe
2. Inno Setup → CleanShotSetup.exe (free)
3. Code signing certificate (needed for Windows SmartScreen)
4. Auto-update via updater.py (already built)

### Fleet Dashboard
`core/subscription.py` has fleet tier defined.
Dispatcher web interface showing all trucks on a map.
Needs backend + web frontend (separate project).

### FMCSA Open Data Integration
Free public data at ai.fmcsa.dot.gov:
- Carrier safety ratings
- Inspection history
- HOS violation patterns
Could add "carrier risk score" to CleanShot Pro features.

### National Bridge Inventory Direct Feed
Raw federal NBI data at data.transportation.gov
Cross-reference with Road511 bridge data for validation.
Adds confidence to clearance checks.

### Road Surface Temperature
roadconditions.com API — black ice prediction
Better than just weather temperature for ice warnings.

---

## 📝 Notes for Next Session

- All work in: `D:\weather-cli\clean-shot` (not the old Documents path)
- Road511 API key: set via `cleanshot settings road511-key <key>`
  or env var `R511_API_KEY` (already in Windows User env vars)
- Current version: 3.0.9 — 420/420 tests passing
- GitHub: github.com/arbymcpatriot3/weather-cli
- Contact: R. Bruce McCarthy — cleanshothq@pm.me

---

## 🧪 Live Integration Testing — Road511 Validation

**Goal:** Prove CleanShot sees what Road511 sees — not just that the code runs,
but that real hazards on real roads show up correctly for real truckers.

### Test Plan

1. **Find active incidents on Road511**
   - Log into road511.com dashboard
   - Find 2-3 currently active incidents (construction, closure, bridge issue)
   - Note the exact location (highway, mile marker, lat/lon if available)

2. **Plan test routes through the trouble area**
   - Route A: Origin → just before the incident (should show warning ahead)
   - Route B: Origin → through the incident area (should show on-route hazard)
   - Route C: Origin → past the incident (should still flag it on the corridor)

3. **Run CleanShot against each route**
   ```
   cleanshot route "destination near incident"
   cleanshot route "destination past incident"
   cleanshot bridges   (if incident is a bridge)
   cleanshot weigh     (if incident is a weigh station)
   ```

4. **Verify CleanShot output matches Road511 dashboard**
   - Does the incident appear?
   - Is the severity correct (critical/major/moderate)?
   - Is the road and direction correct?
   - Is the bridge clearance flagged if applicable?
   - Does safe=False trigger correctly?
   - Does safe=None appear when data is incomplete?

5. **Test edge cases**
   - Incident just outside the corridor buffer (should NOT appear)
   - Incident just inside the buffer (MUST appear)
   - Multiple incidents on same route (all should show)
   - Expired incident (should NOT appear — status=active filter)

6. **Document results**
   - Screenshot Road511 dashboard showing the incident
   - Screenshot CleanShot output for the same route
   - Note any discrepancies for fixing

### Also Test
- 401 error handling (wrong key → clear message not raw error)
- Timeout behavior (throttle connection, verify safe=None not safe=True)
- Cache behavior (run twice — second should be instant from cache)
- All 420 unit tests still pass after any fixes

---

## 💡 Design Principles (Never Forget)

1. **Safety over speed** — safe=None is always better than safe=True when data is uncertain
2. **1.0 ft bridge margin** — federal standard, hard floor of 0.5 ft
3. **Fail open, never crash** — a network error never blocks a trucker
4. **"No data" ≠ "All clear"** — always distinguish between the two
5. **Trucker-first UX** — if they have to ask what something means, we failed
6. **Quality over speed** — 90% confidence minimum before shipping
7. **Every feature in both languages** — English and Spanish, always
