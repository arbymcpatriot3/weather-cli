#!/data/data/com.termux/files/usr/bin/bash
# platforms/android/install_termux.sh — Clean Shot: Driver Intelligence System
# Blue Collar Nation LLC — cleanshothq.com
#
# One-line install in Termux:
#   curl -fsSL 
curl -fsSL https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/clean-shot/platforms/android/install_termux.sh \ | bash

INSTALL_DIR="$HOME/CleanShot"
BIN_DIR="$HOME/bin"
REPO_URL="https://github.com/arbymcpatriot3/weather-cli.git"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { printf "${GREEN}  [OK]  %s${NC}\n" "$1"; }
warn() { printf "${YELLOW}  [!]   %s${NC}\n" "$1"; }
info() { printf "        %s\n" "$1"; }

# ── Banner ─────────────────────────────────────────────────────────────────────
printf "\n"
printf "${CYAN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
printf "${CYAN}  🚛 CLEAN SHOT                       ${NC}\n"
printf "${CYAN}     Driver Intelligence System       ${NC}\n"
printf "     By Blue Collar Nation LLC\n"
printf "     cleanshothq.com\n"
printf "${CYAN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n\n"

# ── Verify Termux environment ──────────────────────────────────────────────────
if [ -z "${PREFIX:-}" ] || [ ! -d "${PREFIX}/bin" ]; then
    printf "\n  This installer runs inside Termux.\n"
    printf "  Download Termux free from F-Droid:\n"
    printf "  https://f-droid.org/packages/com.termux/\n\n"
    exit 1
fi

# ── F-Droid recommendation — show BEFORE doing anything else ──────────────────
printf "${YELLOW}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
printf "${YELLOW}  ⚠️  IMPORTANT — READ FIRST:          ${NC}\n\n"
printf "  For best Clean Shot experience\n"
printf "  use Termux from F-Droid\n"
printf "  NOT from Google Play.\n\n"
printf "  F-Droid Termux has:\n"
printf "${GREEN}  ✅ Full GPS support${NC}\n"
printf "${GREEN}  ✅ All voice features${NC}\n"
printf "${GREEN}  ✅ Latest updates${NC}\n\n"
printf "  Download F-Droid Termux:\n"
printf "  https://f-droid.org\n"
printf "  Search: Termux\n\n"

# Detect Google Play vs F-Droid
TERMUX_IS_GOOGLE_PLAY=0
if echo "${TERMUX_VERSION:-}" | grep -qi "googleplay"; then
    TERMUX_IS_GOOGLE_PLAY=1
fi

if [ "$TERMUX_IS_GOOGLE_PLAY" = "1" ]; then
    printf "${YELLOW}  ⚠️  Google Play Termux detected.    ${NC}\n"
    printf "     GPS may be limited.\n"
    printf "     Clean Shot will still work.\n\n"
else
    printf "${GREEN}  ✅ F-Droid Termux — full GPS ready  ${NC}\n\n"
fi

printf "  Press Enter to continue...\n"
read -r _

printf "${YELLOW}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n\n"

# ── Fix TMPDIR ─────────────────────────────────────────────────────────────────
export TMPDIR="${TMPDIR:-${PREFIX}/tmp}"
mkdir -p "$TMPDIR"

# ── STEP 1: SSL certificates — MUST be first or curl/git will fail ─────────────
printf "\n"
info "Installing SSL certificates..."
pkg install -y ca-certificates openssl-tool 2>/dev/null || true
ok "SSL certificates ready"

# ── STEP 2: Update packages ────────────────────────────────────────────────────
info "Updating package list..."
pkg update -y 2>/dev/null || pkg update 2>/dev/null || true
ok "Packages updated"

# ── STEP 3: Install Python, Git, termux-api ───────────────────────────────────
info "Installing Python, Git, termux-api..."
pkg install -y python git termux-api 2>/dev/null || \
    pkg install -y python git 2>/dev/null || \
    pkg install python git 2>/dev/null || true
ok "Python, Git, termux-api installed"

info "Installing sox (alert tones)..."
pkg install -y sox 2>/dev/null || true
if command -v play &>/dev/null; then
    ok "sox installed — alert tones ready"
else
    warn "sox not available — tones skipped (voice alerts still work)"
fi

# ── STEP 4: Install Python packages ───────────────────────────────────────────
info "Installing Python packages..."
pip install --upgrade pip --quiet 2>/dev/null || true
pip install requests colorama --quiet --break-system-packages 2>/dev/null || \
    pip install requests colorama --quiet 2>/dev/null || \
    pip install requests colorama 2>/dev/null || true
ok "requests, colorama installed"

# ── STEP 4b: Try piper-tts on aarch64 (optional upgrade) ─────────────────────
ARCH=$(uname -m 2>/dev/null || echo "unknown")
if [ "$ARCH" = "aarch64" ]; then
    info "Trying piper-tts for Android (aarch64)..."
    pip install piper-tts --quiet --break-system-packages 2>/dev/null || \
        pip install piper-tts --quiet 2>/dev/null || true
    if python3 -c "from piper import PiperVoice" 2>/dev/null; then
        ok "piper-tts installed — downloading voice model..."
        PIPER_DIR="$HOME/.local/share/piper"
        mkdir -p "$PIPER_DIR"
        VOICE_NAME="en_US-ryan-high"
        HF_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/high"
        DOWNLOAD_OK=true
        curl -fsSL -o "$PIPER_DIR/$VOICE_NAME.onnx" "$HF_BASE/$VOICE_NAME.onnx" 2>/dev/null || \
            wget -q -O "$PIPER_DIR/$VOICE_NAME.onnx" "$HF_BASE/$VOICE_NAME.onnx" 2>/dev/null || \
            { DOWNLOAD_OK=false; rm -f "$PIPER_DIR/$VOICE_NAME.onnx"; }
        if [ "$DOWNLOAD_OK" = true ]; then
            curl -fsSL -o "$PIPER_DIR/$VOICE_NAME.onnx.json" "$HF_BASE/$VOICE_NAME.onnx.json" 2>/dev/null || \
                wget -q -O "$PIPER_DIR/$VOICE_NAME.onnx.json" "$HF_BASE/$VOICE_NAME.onnx.json" 2>/dev/null || \
                { DOWNLOAD_OK=false; }
        fi
        if [ "$DOWNLOAD_OK" = true ] && [ -f "$PIPER_DIR/$VOICE_NAME.onnx" ]; then
            ok "Voice model downloaded: $VOICE_NAME ⭐⭐⭐⭐⭐"
        else
            warn "Voice model download failed — device TTS will be used"
            rm -f "$PIPER_DIR/$VOICE_NAME.onnx" "$PIPER_DIR/$VOICE_NAME.onnx.json" 2>/dev/null || true
        fi
    else
        info "piper-tts not available — using device TTS (termux-tts-speak)"
    fi
fi

# ── STEP 5: Clone or update repo ──────────────────────────────────────────────
printf "\n"
info "Setting up Clean Shot..."
if [ -d "$INSTALL_DIR/.git" ]; then
    info "Updating existing installation..."
    git -C "$INSTALL_DIR" pull --quiet 2>/dev/null || true
    ok "Updated to latest version"
else
    info "Downloading Clean Shot..."
    [ -d "$INSTALL_DIR" ] && rm -rf "$INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR" --quiet
    ok "Clean Shot downloaded"
fi

# ── STEP 6: Fix TMPDIR permanently ────────────────────────────────────────────
BASHRC="$HOME/.bashrc"
touch "$BASHRC"
if ! grep -q "TMPDIR" "$BASHRC" 2>/dev/null; then
    printf '\n# Clean Shot\nexport TMPDIR="${PREFIX}/tmp"\n' >> "$BASHRC"
    ok "TMPDIR added to ~/.bashrc"
fi

# ── STEP 7: Create cleanshot launcher ─────────────────────────────────────────
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/cleanshot" << 'LAUNCHER'
#!/usr/bin/env bash
export TMPDIR="${TMPDIR:-${PREFIX:-/data/data/com.termux/files/usr}/tmp}"
export CLEANSHOT_CMD=cleanshot
cd "$HOME/CleanShot/clean-shot"
exec python3 platforms/android/main.py "$@"
LAUNCHER
chmod +x "$BIN_DIR/cleanshot"
ok "Launcher: $BIN_DIR/cleanshot"

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    printf '\nexport PATH="$HOME/bin:$PATH"\n' >> "$BASHRC"
    ok "~/bin added to PATH"
fi
export PATH="$BIN_DIR:$PATH"

# ── STEP 8: Auto voice setup ───────────────────────────────────────────────────
printf "\n"
info "Setting up voice system..."
python3 -c "
import sys, shutil
sys.path.insert(0, '$INSTALL_DIR/clean-shot')
# Check voice engine
tts_ok = shutil.which('termux-tts-speak')
piper_ok = False
try:
    from piper import PiperVoice
    from pathlib import Path
    piper_dir = Path.home() / '.local' / 'share' / 'piper'
    piper_ok = (piper_dir / 'en_US-ryan-high.onnx').exists()
except Exception:
    pass
if piper_ok:
    print('  [OK]  Voice: piper-tts en_US-ryan-high ⭐⭐⭐⭐⭐')
elif tts_ok:
    print('  [OK]  Voice: termux-tts-speak (device TTS) ⭐⭐⭐')
else:
    print('  [!]   termux-tts-speak not found')
    print('        Fix: pkg install termux-api')
" 2>/dev/null || true

# ── STEP 9: Run doctor ─────────────────────────────────────────────────────────
printf "\n"
info "Checking Clean Shot..."
(cd "$INSTALL_DIR/clean-shot" && python3 platforms/android/main.py doctor 2>/dev/null) || true

# ── Success ────────────────────────────────────────────────────────────────────
printf "\n"
printf "${GREEN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
printf "${GREEN}  Clean Shot installed!               ${NC}\n\n"
printf "  For help:  cleanshot help\n"
printf "  Support:   support@cleanshothq.com\n"
printf "${GREEN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n\n"

# ── Launch Clean Shot ──────────────────────────────────────────────────────────
printf "  Starting Clean Shot...\n\n"
exec cleanshot 2>/dev/null || \
    (cd "$INSTALL_DIR/clean-shot" && exec python3 platforms/android/main.py)
