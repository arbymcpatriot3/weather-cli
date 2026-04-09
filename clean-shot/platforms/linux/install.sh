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
    info "Installing Python 3..."
    # Update index first so installs succeed
    case "$PKG_MGR" in
        apt-get|apt) $SUDO_CMD "$PKG_MGR" update -qq 2>/dev/null || true ;;
    esac
    install_pkg python3
    install_pkg python3-pip
    install_pkg python3-venv
    for cmd in python3 python3.11 python3.10; do
        command -v "$cmd" &>/dev/null && { PYTHON="$cmd"; break; }
    done
fi

[ -z "$PYTHON" ] && PYTHON="python3"
ver=$("$PYTHON" -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')" 2>/dev/null || echo "3")
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

# ── STEP 4: Install espeak (TTS engine) ───────────────────────────────────────
info "Checking audio (TTS)..."
if ! command -v espeak &>/dev/null && ! command -v espeak-ng &>/dev/null; then
    install_pkg espeak-ng 2>/dev/null || install_pkg espeak 2>/dev/null || true
fi
ok "Audio ready"

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
printf "\n"
info "Installing Python packages..."
"$PYTHON" -m pip install --upgrade pip --quiet 2>/dev/null || true
"$PYTHON" -m pip install requests colorama pyttsx3 --quiet --user 2>/dev/null || \
    "$PYTHON" -m pip install requests colorama pyttsx3 --quiet --break-system-packages 2>/dev/null || \
    "$PYTHON" -m pip install requests colorama pyttsx3 --quiet 2>/dev/null || true
ok "Packages installed (requests, colorama, pyttsx3)"

# ── STEP 7: Create cleanshot command ──────────────────────────────────────────
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

# ── STEP 8: Run doctor ────────────────────────────────────────────────────────
printf "\n"
info "Checking Clean Shot..."
(cd "$INSTALL_DIR/clean-shot" && "$PYTHON" platforms/linux/main.py doctor 2>/dev/null) || true

# ── Success ────────────────────────────────────────────────────────────────────
printf "\n"
printf "${GREEN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
printf "${GREEN}  Clean Shot installed!               ${NC}\n\n"
printf "  Open a new terminal and type:\n"
printf "${CYAN}    cleanshot${NC}\n\n"
printf "  For help:  cleanshot help\n"
printf "  Support:   support@cleanshothq.com\n"
printf "${GREEN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n\n"
