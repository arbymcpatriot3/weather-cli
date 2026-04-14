#!/usr/bin/env bash
# platforms/linux/install.sh — Clean Shot Linux Installer
# Blue Collar Nation LLC — cleanshothq.com
#
# One-line install:
#   curl -fsSL https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/clean-shot/platforms/linux/install.sh | bash

set -e

INSTALL_DIR="$HOME/CleanShot"
REPO_URL="https://github.com/arbymcpatriot3/weather-cli.git"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { printf "${GREEN}  [OK]  %s${NC}\n" "$1"; }
warn() { printf "${YELLOW}  [!]   %s${NC}\n" "$1"; }
info() { printf "        %s\n" "$1"; }

# ── Header ─────────────────────────────────────────────────────────────────────
printf "\n"
printf "${CYAN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
printf "${CYAN}  Clean Shot — Linux Installer        ${NC}\n"
printf "  Built for the road, not the boardroom\n"
printf "${CYAN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n\n"

# ── STEP 1: Detect package manager ────────────────────────────────────────────
PKG_MGR=""
SUDO_CMD=""
command -v sudo &>/dev/null && SUDO_CMD="sudo"

if   command -v apt-get &>/dev/null; then PKG_MGR="apt-get"
elif command -v apt     &>/dev/null; then PKG_MGR="apt"
elif command -v dnf     &>/dev/null; then PKG_MGR="dnf"
elif command -v yum     &>/dev/null; then PKG_MGR="yum"
elif command -v pacman  &>/dev/null; then PKG_MGR="pacman"
elif command -v zypper  &>/dev/null; then PKG_MGR="zypper"
elif command -v apk     &>/dev/null; then PKG_MGR="apk"
fi

install_pkg() {
    local pkg="$1"
    case "$PKG_MGR" in
        apt-get|apt)
            $SUDO_CMD "$PKG_MGR" install -y "$pkg" -q 2>/dev/null || \
            $SUDO_CMD "$PKG_MGR" install -y "$pkg" 2>/dev/null || true ;;
        dnf|yum)
            $SUDO_CMD "$PKG_MGR" install -y "$pkg" -q 2>/dev/null || \
            $SUDO_CMD "$PKG_MGR" install -y "$pkg" 2>/dev/null || true ;;
        pacman)
            $SUDO_CMD pacman -S --noconfirm "$pkg" 2>/dev/null || true ;;
        zypper)
            $SUDO_CMD zypper install -y "$pkg" 2>/dev/null || true ;;
        apk)
            $SUDO_CMD apk add --quiet "$pkg" 2>/dev/null || true ;;
        *)
            true ;;
    esac
}

# ── STEP 2: Install Python ─────────────────────────────────────────────────────
info "Checking Python..."
PYTHON=""
for cmd in python3 python3.11 python3.10 python3.9 python3.8; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')" 2>/dev/null || true)
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -eq 3 ] && [ "$minor" -ge 8 ] 2>/dev/null; then
            PYTHON="$cmd"; break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    info "Installing Python 3.11..."
    # Update index first so installs succeed
    case "$PKG_MGR" in
        apt-get|apt) $SUDO_CMD "$PKG_MGR" update -qq 2>/dev/null || true ;;
        dnf|yum)     $SUDO_CMD "$PKG_MGR" check-update -q 2>/dev/null || true ;;
    esac
    # Try python3.11 first, fall back to any python3
    install_pkg python3.11 2>/dev/null || true
    install_pkg python3
    install_pkg python3-pip
    install_pkg python3-venv
    for cmd in python3.11 python3.10 python3.9 python3; do
        command -v "$cmd" &>/dev/null && { PYTHON="$cmd"; break; }
    done
fi

[ -z "$PYTHON" ] && PYTHON="python3"
ver=$("$PYTHON" -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')" 2>/dev/null || echo "3")
minor_ver=$("$PYTHON" -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo "0")
if [ "$minor_ver" -ge 13 ] 2>/dev/null; then
    warn "Python $ver detected — Python 3.11 is recommended for best compatibility"
    warn "Clean Shot works but pyttsx3 TTS may not work on Python 3.13+"
fi
ok "Python $ver ready"

# ── Ensure pip ────────────────────────────────────────────────────────────────
if ! "$PYTHON" -m pip --version &>/dev/null; then
    info "Installing pip..."
    install_pkg python3-pip
    "$PYTHON" -m ensurepip --upgrade 2>/dev/null || true
    curl -fsSL https://bootstrap.pypa.io/get-pip.py | "$PYTHON" 2>/dev/null || true
fi

# ── STEP 3: Install Git ───────────────────────────────────────────────────────
info "Checking Git..."
if ! command -v git &>/dev/null; then
    info "Installing Git..."
    install_pkg git
fi
ok "Git ready"

# ── STEP 4: Install TTS engines ───────────────────────────────────────────────
# espeak-ng = standard (always install as fallback)
# festival + festvox-us-slt-hts = enhanced (much more natural voice)
printf "\n"
info "Installing TTS engines (voice alerts)..."
case "$PKG_MGR" in
    apt-get|apt)
        $SUDO_CMD "$PKG_MGR" install -y \
            espeak-ng libespeak-ng1 python3-dev gcc \
            festival festvox-us-slt-hts \
            -q 2>/dev/null || \
        $SUDO_CMD "$PKG_MGR" install -y \
            espeak-ng libespeak-ng1 festival \
            -q 2>/dev/null || \
        $SUDO_CMD "$PKG_MGR" install -y espeak-ng 2>/dev/null || true ;;
    dnf|yum)
        $SUDO_CMD "$PKG_MGR" install -y espeak-ng festival python3-devel -q 2>/dev/null || \
        $SUDO_CMD "$PKG_MGR" install -y espeak-ng 2>/dev/null || true ;;
    pacman)
        $SUDO_CMD pacman -S --noconfirm espeak-ng festival 2>/dev/null || \
        $SUDO_CMD pacman -S --noconfirm espeak-ng 2>/dev/null || true ;;
    zypper)
        $SUDO_CMD zypper install -y espeak-ng festival 2>/dev/null || \
        $SUDO_CMD zypper install -y espeak-ng 2>/dev/null || true ;;
    *) true ;;
esac

if command -v festival &>/dev/null; then
    ok "TTS engines installed (festival + espeak-ng)"
elif command -v espeak-ng &>/dev/null || command -v espeak &>/dev/null; then
    ok "TTS engine installed (espeak-ng — enhanced quality requires festival)"
    warn "For better voice: sudo apt-get install -y festival festvox-us-slt-hts"
else
    warn "TTS engine not installed — voice alerts disabled until fixed"
    warn "Fix: sudo apt-get install -y espeak-ng libespeak-ng1 festival"
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

# ── STEP 6: Install Python packages ───────────────────────────────────────────
# --break-system-packages is required on Linux Mint 21+, Ubuntu 22.04+, Debian 12+
# (PEP 668 "externally managed environment"). Try it first, fall back to --user.
printf "\n"
info "Installing Python packages (requests, colorama, pyttsx3)..."
"$PYTHON" -m pip install --upgrade pip --quiet --break-system-packages 2>/dev/null || \
    "$PYTHON" -m pip install --upgrade pip --quiet 2>/dev/null || true

"$PYTHON" -m pip install requests colorama pyttsx3 --quiet --break-system-packages 2>/dev/null || \
    "$PYTHON" -m pip install requests colorama pyttsx3 --quiet --user 2>/dev/null || \
    "$PYTHON" -m pip install requests colorama pyttsx3 --quiet 2>/dev/null || true

if "$PYTHON" -c "import pyttsx3" 2>/dev/null; then
    ok "Packages installed (requests, colorama, pyttsx3)"
else
    warn "pyttsx3 not installed — voice alerts will use text fallback"
    warn "Fix: sudo apt-get install -y espeak-ng libespeak-ng1"
    warn "     pip3 install pyttsx3 --break-system-packages"
fi

# ── STEP 7a: Install piper-tts (neural voice — most natural) ──────────────────
printf "\n"
info "Installing piper-tts (neural voice engine)..."
"$PYTHON" -m pip install piper-tts --quiet --break-system-packages 2>/dev/null || \
    "$PYTHON" -m pip install piper-tts --quiet --user 2>/dev/null || \
    "$PYTHON" -m pip install piper-tts --quiet 2>/dev/null || true

if "$PYTHON" -c "from piper import PiperVoice" 2>/dev/null; then
    ok "piper-tts installed"

    # Download default voice model: en_US-lessac-medium (~60MB)
    PIPER_DIR="$HOME/.local/share/piper"
    VOICE_NAME="en_US-lessac-medium"
    VOICE_ONNX="$PIPER_DIR/$VOICE_NAME.onnx"
    VOICE_JSON="$PIPER_DIR/$VOICE_NAME.onnx.json"
    HF_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium"

    if [ -f "$VOICE_ONNX" ] && [ -f "$VOICE_JSON" ]; then
        ok "Voice model already installed: $VOICE_NAME"
    else
        mkdir -p "$PIPER_DIR"
        info "Downloading voice model: $VOICE_NAME (~60MB)..."
        info "This is a one-time download — truckers deserve a natural voice."

        DOWNLOAD_OK=true
        curl -fsSL -o "$VOICE_ONNX" "$HF_BASE/$VOICE_NAME.onnx" 2>/dev/null || \
            wget -q -O "$VOICE_ONNX" "$HF_BASE/$VOICE_NAME.onnx" 2>/dev/null || \
            { DOWNLOAD_OK=false; rm -f "$VOICE_ONNX"; }

        if [ "$DOWNLOAD_OK" = true ]; then
            curl -fsSL -o "$VOICE_JSON" "$HF_BASE/$VOICE_NAME.onnx.json" 2>/dev/null || \
                wget -q -O "$VOICE_JSON" "$HF_BASE/$VOICE_NAME.onnx.json" 2>/dev/null || \
                { DOWNLOAD_OK=false; rm -f "$VOICE_JSON"; }
        fi

        if [ "$DOWNLOAD_OK" = true ] && [ -f "$VOICE_ONNX" ] && [ -f "$VOICE_JSON" ]; then
            ok "Voice model downloaded: $VOICE_NAME ⭐⭐⭐⭐⭐"
        else
            warn "Voice model download failed — festival/espeak will be used"
            warn "Download later: cleanshot voices download"
            rm -f "$VOICE_ONNX" "$VOICE_JSON" 2>/dev/null || true
        fi
    fi
else
    warn "piper-tts not installed — festival/espeak fallback active"
    warn "Install manually: pip3 install piper-tts --break-system-packages"
    warn "Download voice:   cleanshot voices download"
fi

# ── STEP 8: Create cleanshot command ──────────────────────────────────────────
SYSTEM_BIN="/usr/local/bin/cleanshot"
USER_BIN="$HOME/.local/bin/cleanshot"
LAUNCHER_BODY="$(printf '#!/usr/bin/env bash\nexport CLEANSHOT_CMD=cleanshot\ncd "%s/clean-shot"\nexec %s platforms/linux/main.py "$@"\n' "$INSTALL_DIR" "$PYTHON")"

if printf '%s\n' "$LAUNCHER_BODY" | $SUDO_CMD tee "$SYSTEM_BIN" > /dev/null 2>&1; then
    $SUDO_CMD chmod +x "$SYSTEM_BIN" 2>/dev/null || true
    ok "Launcher: $SYSTEM_BIN"
else
    mkdir -p "$HOME/.local/bin"
    printf '%s\n' "$LAUNCHER_BODY" > "$USER_BIN"
    chmod +x "$USER_BIN"
    for RC in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
        [ -f "$RC" ] || continue
        grep -q 'local/bin' "$RC" 2>/dev/null && break
        printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$RC"
        break
    done
    export PATH="$HOME/.local/bin:$PATH"
    ok "Launcher: $USER_BIN"
fi

# ── STEP 9: Run doctor ────────────────────────────────────────────────────────
printf "\n"
info "Checking Clean Shot..."
(cd "$INSTALL_DIR/clean-shot" && "$PYTHON" platforms/linux/main.py doctor 2>/dev/null) || true

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
    (cd "$INSTALL_DIR/clean-shot" && exec "$PYTHON" platforms/linux/main.py)
