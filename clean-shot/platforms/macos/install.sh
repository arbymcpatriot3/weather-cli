#!/usr/bin/env bash
# platforms/macos/install.sh — Clean Shot macOS Installer
# Blue Collar Nation LLC — cleanshothq.com
#
# One-line install:
#   curl -fsSL https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/clean-shot/platforms/macos/install.sh | bash

set -e

INSTALL_DIR="$HOME/CleanShot"
REPO_URL="https://github.com/arbymcpatriot3/weather-cli.git"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { printf "${GREEN}  [OK]  %s${NC}\n" "$1"; }
warn() { printf "${YELLOW}  [!]   %s${NC}\n" "$1"; }
info() { printf "        %s\n" "$1"; }

# ── Header ─────────────────────────────────────────────────────────────────────
printf "\n"
printf "${CYAN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
printf "${CYAN}  Clean Shot — macOS Installer        ${NC}\n"
printf "  Built for the road, not the boardroom\n"
printf "${CYAN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n\n"

# ── STEP 1: Xcode Command Line Tools ──────────────────────────────────────────
if ! xcode-select -p &>/dev/null; then
    info "Installing developer tools..."
    info "Click Install when the dialog appears."
    xcode-select --install 2>/dev/null || true
    until xcode-select -p &>/dev/null; do sleep 5; done
    ok "Developer tools installed"
else
    ok "Developer tools ready"
fi

# ── STEP 2: Homebrew ───────────────────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
    printf "\n"
    printf "  ┌─────────────────────────────────────┐\n"
    printf "  │  Your Mac password is required      │\n"
    printf "  │  to install Homebrew.               │\n"
    printf "  │                                     │\n"
    printf "  │  This is normal and safe.           │\n"
    printf "  │  Homebrew takes 5-10 minutes        │\n"
    printf "  │  on first install.                  │\n"
    printf "  └─────────────────────────────────────┘\n"
    printf "\n"
    info "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Add to PATH — Apple Silicon (M1/M2/M3/M4) or Intel
    if [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> "$HOME/.zprofile" 2>/dev/null || true
    elif [ -f /usr/local/bin/brew ]; then
        eval "$(/usr/local/bin/brew shellenv)"
        echo 'eval "$(/usr/local/bin/brew shellenv)"' >> "$HOME/.zprofile" 2>/dev/null || true
    fi
    ok "Homebrew installed"
else
    ok "Homebrew ready"
fi

# ── STEP 3: Python 3.11 ───────────────────────────────────────────────────────
PYTHON=""
for cmd in python3.11 python3.12 python3.10 python3.9 python3; do
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
    brew install python@3.11
    for candidate in \
        "$(brew --prefix 2>/dev/null)/bin/python3.11" \
        /opt/homebrew/bin/python3.11 \
        /opt/homebrew/opt/python@3.11/bin/python3.11 \
        /usr/local/bin/python3.11 \
        /usr/local/opt/python@3.11/bin/python3.11; do
        [ -x "$candidate" ] && { PYTHON="$candidate"; break; }
    done
    [ -z "$PYTHON" ] && PYTHON="python3.11"
    ok "Python 3.11 installed"
else
    ver=$("$PYTHON" -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')" 2>/dev/null || echo "3")
    ok "Python $ver ready"
fi

# ── STEP 4: Git ───────────────────────────────────────────────────────────────
if ! command -v git &>/dev/null; then
    info "Installing Git..."
    brew install git
    ok "Git installed"
else
    ok "Git ready"
fi

# ── STEP 5: Clone or update repo ──────────────────────────────────────────────
printf "\n"
if [ -d "$INSTALL_DIR/.git" ]; then
    info "Updating Clean Shot..."
    git -C "$INSTALL_DIR" pull --quiet 2>/dev/null || true
    ok "Updated to latest version"
else
    info "Downloading Clean Shot..."
    [ -d "$INSTALL_DIR" ] && rm -rf "$INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR" --quiet
    ok "Clean Shot downloaded"
fi

# ── STEP 6: Python packages ───────────────────────────────────────────────────
printf "\n"
info "Installing Python packages..."
"$PYTHON" -m ensurepip --upgrade --quiet 2>/dev/null || true
"$PYTHON" -m pip install --upgrade pip --quiet 2>/dev/null || true
"$PYTHON" -m pip install requests colorama --quiet 2>/dev/null || \
    "$PYTHON" -m pip install requests colorama --quiet --break-system-packages 2>/dev/null || \
    "$PYTHON" -m pip install requests colorama --quiet --user 2>/dev/null || true
ok "Packages installed (requests, colorama)"

# ── STEP 7: Create cleanshot command ──────────────────────────────────────────
LAUNCHER="/usr/local/bin/cleanshot"
{
    printf '#!/usr/bin/env bash\nexport CLEANSHOT_CMD=cleanshot\ncd "%s/clean-shot"\nexec %s platforms/linux/main.py "$@"\n' \
        "$INSTALL_DIR" "$PYTHON"
} | sudo tee "$LAUNCHER" > /dev/null 2>&1 && sudo chmod +x "$LAUNCHER" 2>/dev/null || {
    # No sudo — use user bin
    mkdir -p "$HOME/.local/bin"
    LAUNCHER="$HOME/.local/bin/cleanshot"
    printf '#!/usr/bin/env bash\nexport CLEANSHOT_CMD=cleanshot\ncd "%s/clean-shot"\nexec %s platforms/linux/main.py "$@"\n' \
        "$INSTALL_DIR" "$PYTHON" > "$LAUNCHER"
    chmod +x "$LAUNCHER"
    # Add to PATH in all shell profiles
    for RC in "$HOME/.zshrc" "$HOME/.zprofile" "$HOME/.bash_profile" "$HOME/.bashrc"; do
        [ -f "$RC" ] || continue
        grep -q 'local/bin' "$RC" 2>/dev/null && break
        printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$RC"
        break
    done
    export PATH="$HOME/.local/bin:$PATH"
}
ok "Launcher: $LAUNCHER"

# ── STEP 8: Run doctor ────────────────────────────────────────────────────────
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
