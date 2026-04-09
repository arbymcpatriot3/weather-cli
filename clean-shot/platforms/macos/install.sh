#!/usr/bin/env bash
# platforms/macos/install.sh — Clean Shot macOS Installer
# Blue Collar Nation LLC — cleanshothq.com
#
# One-line install:
#   curl -fsSL https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/clean-shot/platforms/macos/install.sh | bash

set -euo pipefail

INSTALL_DIR="$HOME/CleanShot"
REPO_URL="https://github.com/arbymcpatriot3/weather-cli.git"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

ok()   { printf "${GREEN}  [OK]  %s${NC}\n" "$1"; }
warn() { printf "${YELLOW}  [!]   %s${NC}\n" "$1"; }
info() { printf "        %s\n" "$1"; }
die()  {
    printf "\n${RED}  [ERR] %s${NC}\n\n" "$1"
    printf "  Need help? support@cleanshothq.com\n"
    printf "  cleanshothq.com\n\n"
    exit 1
}

# ── Header ─────────────────────────────────────────────────────────────────────
printf "\n"
printf "${CYAN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
printf "${CYAN}  Clean Shot — macOS Installer        ${NC}\n"
printf "  Built for the road, not the boardroom\n"
printf "${CYAN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n\n"

# ── STEP 1: Install Homebrew if needed ────────────────────────────────────────
info "Checking Homebrew..."
if ! command -v brew &>/dev/null; then
    info "Homebrew not found. Installing (you may be prompted for your password)..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || \
        die "Homebrew install failed. Visit https://brew.sh and install manually, then re-run."

    # Add brew to PATH — handles both Intel and Apple Silicon
    if [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> "$HOME/.zprofile" 2>/dev/null || true
    elif [ -f /usr/local/bin/brew ]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi
    ok "Homebrew installed"
else
    ok "Homebrew found"
fi

# ── STEP 2: Install Python 3.11 ───────────────────────────────────────────────
info "Checking Python..."
PYTHON3=""

# Check for a usable Python (prefer 3.11, accept 3.8-3.13)
for cmd in python3.11 python3.12 python3.10 python3.9 python3 python3.8; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -eq 3 ] && [ "$minor" -ge 8 ] && [ "$minor" -le 13 ] 2>/dev/null; then
            PYTHON3="$cmd"; break
        fi
    fi
done

if [ -z "$PYTHON3" ]; then
    info "Installing Python 3.11 via Homebrew..."
    brew install python@3.11 --quiet 2>/dev/null || \
        brew install python@3.11 2>&1 | tail -3 || \
        die "Python install failed. Run: brew install python@3.11"

    # Find newly installed python
    for candidate in \
        /opt/homebrew/bin/python3.11 \
        /opt/homebrew/opt/python@3.11/bin/python3.11 \
        /usr/local/bin/python3.11 \
        /usr/local/opt/python@3.11/bin/python3.11; do
        [ -x "$candidate" ] && { PYTHON3="$candidate"; break; }
    done
    [ -z "$PYTHON3" ] && PYTHON3="python3.11"
    ok "Python 3.11 installed"
else
    ver=$("$PYTHON3" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "unknown")
    ok "Python $ver found: $PYTHON3"
fi

# ── STEP 3: Install Git if needed ─────────────────────────────────────────────
info "Checking Git..."
if ! command -v git &>/dev/null; then
    info "Installing Git via Homebrew..."
    brew install git --quiet 2>/dev/null || brew install git 2>&1 | tail -3 || \
        die "Git install failed. Run: brew install git"
    ok "Git installed"
else
    ok "Git found"
fi

# ── STEP 4: Clone or update repo ──────────────────────────────────────────────
printf "\n"
info "Setting up Clean Shot..."
if [ -f "$INSTALL_DIR/clean-shot/platforms/linux/main.py" ]; then
    info "Updating existing installation..."
    git -C "$INSTALL_DIR" pull --quiet 2>/dev/null || warn "Could not update — using existing version"
    ok "Updated to latest version"
else
    info "Downloading Clean Shot (about 10 seconds)..."
    [ -d "$INSTALL_DIR" ] && rm -rf "$INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR" --quiet 2>/dev/null || \
        git clone "$REPO_URL" "$INSTALL_DIR" 2>&1 | tail -1 || true
    [ -f "$INSTALL_DIR/clean-shot/platforms/linux/main.py" ] || \
        die "Download failed. Check your internet connection and try again."
    ok "Clean Shot downloaded to: $INSTALL_DIR"
fi

# ── STEP 5: Install Python packages ───────────────────────────────────────────
printf "\n"
info "Installing Python packages..."
"$PYTHON3" -m pip install requests colorama --quiet 2>/dev/null || \
    "$PYTHON3" -m pip install requests colorama --quiet --break-system-packages 2>/dev/null || \
    warn "Package install had issues. Run: $PYTHON3 -m pip install requests colorama"
ok "Packages installed (requests, colorama)"

# ── STEP 6: Create cleanshot command ──────────────────────────────────────────
# Handle both Intel (/usr/local) and Apple Silicon (/opt/homebrew)
BREW_BIN=""
[ -d /opt/homebrew/bin ] && BREW_BIN="/opt/homebrew/bin"
[ -d /usr/local/bin ]    && BREW_BIN="${BREW_BIN:-/usr/local/bin}"

LAUNCHER="/usr/local/bin/cleanshot"
printf '#!/usr/bin/env bash\nexport CLEANSHOT_CMD=cleanshot\ncd "$HOME/CleanShot/clean-shot"\nexec %s platforms/linux/main.py "$@"\n' "$PYTHON3" | \
    sudo tee "$LAUNCHER" > /dev/null 2>&1 || {
    # No sudo — try user bin
    mkdir -p "$HOME/.local/bin"
    LAUNCHER="$HOME/.local/bin/cleanshot"
    printf '#!/usr/bin/env bash\nexport CLEANSHOT_CMD=cleanshot\ncd "$HOME/CleanShot/clean-shot"\nexec %s platforms/linux/main.py "$@"\n' "$PYTHON3" > "$LAUNCHER"

    # Add to PATH
    for RC in "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.bashrc" "$HOME/.profile"; do
        [ -f "$RC" ] || continue
        if ! grep -q 'local/bin' "$RC" 2>/dev/null; then
            printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$RC"
            break
        fi
    done
    warn "Open a new terminal after install (PATH updated)"
}
chmod +x "$LAUNCHER" 2>/dev/null || sudo chmod +x "$LAUNCHER" 2>/dev/null || true
ok "Launcher: $LAUNCHER"

# ── STEP 7: Run doctor ────────────────────────────────────────────────────────
printf "\n"
info "Running system check..."
(cd "$INSTALL_DIR/clean-shot" && "$PYTHON3" platforms/linux/main.py doctor 2>/dev/null) || \
    warn "System check had warnings — run 'cleanshot doctor' after opening a new terminal"

# ── Success ────────────────────────────────────────────────────────────────────
printf "\n"
printf "${GREEN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
printf "${GREEN}  OK  Clean Shot installed!${NC}\n\n"
printf "  Type:          cleanshot\n"
printf "  For help:      cleanshot help\n"
printf "  Check system:  cleanshot doctor\n\n"
printf "  Need help?     support@cleanshothq.com\n"
printf "                 cleanshothq.com\n"
printf "${GREEN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n\n"
