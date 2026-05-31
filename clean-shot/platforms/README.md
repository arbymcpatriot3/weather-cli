# CleanShot — Platform Support

## Current & Planned Platforms

| Platform | Status | Tech | Notes |
|----------|--------|------|-------|
| **Windows 10/11** | ✅ Live | Python + PyInstaller | Primary platform; signed exe via Azure Trusted Signing |
| **Linux / macOS** | ✅ Live | Python (script) | Unified entry point via `platforms/linux/main.py` |
| **Android (Termux)** | ✅ Live | Python (script) | F-Droid Termux recommended; Google Play Termux = IP geo only |
| **iOS (iSH)** | ✅ Live | Python (script) | Alpine Linux emulation; limited TTS (espeak-ng) |
| **macOS (native app)** | 🔄 Planned | Python + Briefcase or py2app | Touch Bar support; notarized via Apple Developer Program |
| **Android (native app)** | 🔄 Planned | Kivy or BeeWare | Touch-friendly UI; GPS via Android Location API |
| **iOS (native app)** | 🔄 Planned | BeeWare Briefcase | App Store submission; AVSpeech for voice alerts |
| **Windows Store (MSIX)** | 🔄 Planned | MSIX packaging | After SmartScreen reputation builds via direct exe |

---

## Entry Points

| Platform | Entry Point | Installer |
|----------|------------|-----------|
| Windows | `platforms/windows/main.py` | `platforms/windows/install.ps1` |
| Linux / macOS | `platforms/linux/main.py` | `platforms/linux/install.sh` (Linux), `platforms/macos/install.sh` (macOS) |
| Android | `platforms/android/main.py` | `platforms/android/install_termux.sh` |
| iOS | `platforms/ios/main.py` | `platforms/ios/install_ish.sh` |

---

## PyInstaller Build (Windows)

The signed Windows exe is built by GitHub Actions on every `v*.*.*` tag:

```bash
pyinstaller clean-shot/cleanshot.spec
```

The spec file at `clean-shot/cleanshot.spec` bundles:
- Entry point: `platforms/windows/main.py`
- All `core/`, `display/`, `claude/`, `platforms/windows/` modules
- i18n JSON files (`core/i18n/en.json`, `core/i18n/es.json`)
- Output: `dist/cleanshot.exe` → signed → uploaded to R2 + GitHub Release

---

## Platform Feature Matrix

| Feature | Windows | Linux/macOS | Android | iOS |
|---------|---------|-------------|---------|-----|
| Weather + Hazards | ✅ | ✅ | ✅ | ✅ |
| DOT/511 | ✅ | ✅ | ✅ | ✅ |
| HOS Guardian | ✅ | ✅ | ✅ | ✅ |
| Parking Runway | ✅ | ✅ | ✅ | ✅ |
| Voice Alerts (TTS) | ✅ pyttsx3/SAPI | ✅ Piper/festival | ✅ termux-tts-speak | ⚠️ espeak-ng |
| GPS (live) | ✅ WinRT | ✅ gpsd | ✅ termux-location (F-Droid) | ❌ config only |
| Continuous Mode | ✅ | ✅ | ⚠️ no keyboard | ⚠️ no keyboard |
| Interactive Menu | ✅ | ✅ | ✅ | ✅ |
| Road Intelligence (road511) | ✅ | ✅ | ✅ | ✅ |

---

## Native App Roadmap Notes

### Android
- **UI**: Kivy (mature) or BeeWare Toga (cleaner Python API)
- **GPS**: Android Location API via Pyjnius or BeeWare
- **TTS**: Android TextToSpeech API
- **Key challenge**: Background service for continuous mode (requires foreground service)

### iOS
- **UI**: BeeWare Briefcase → generates Xcode project
- **Distribution**: App Store (requires Apple Developer Program, $99/yr)
- **TTS**: AVSpeechSynthesizer (native, high quality)
- **Key challenge**: App Store review, no sideloading without trust cert

### Windows Store
- **Packaging**: MSIX via `msix-packaging-tool` or GitHub Actions
- **When to pursue**: After direct exe builds SmartScreen reputation (typically 3–6 months, ~1000 downloads)
- **Benefit**: Automatic updates, no SmartScreen prompt, Windows 11 recommended apps

---

*Updated: 2026-05-30 | CleanShotHQ LLC*
