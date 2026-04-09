#!/usr/bin/env bash
# platforms/android/install_termux.sh — Clean Shot Android/Termux Installer
# Blue Collar Nation LLC — cleanshothq.com
#
# One-line install in Termux:
#   curl -fsSL https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/clean-shot/platforms/android/install_termux.sh | bash

set -e

INSTALL_DIR="$HOME/CleanShot"
BIN_DIR="$HOME/bin"
REPO_URL="https://github.com/arbymcpatriot3/weather-cli.git"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { printf "${GREEN}  [OK]  %s${NC}\n" "$1"; }
warn() { printf "${YELLOW}  [!]   %s${NC}\n" "$1"; }
info() { printf "        %s\n" "$1"; }

# ── Header ─────────────────────────────────────────────────────────────────────
printf "\n"
printf "${CYAN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
printf "${CYAN}  Clean Shot — Android Installer      ${NC}\n"
printf "  Built for the road, not the boardroom\n"
printf "${CYAN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n\n"

# ── Verify Termux environment ──────────────────────────────────────────────────
if [ -z "${PREFIX:-}" ] || [ ! -d "${PREFIX}/bin" ]; then
    printf "\n  This installer runs inside Termux.\n"
    printf "  Download Termux free from F-Droid:\n"
    printf "  https://f-droid.org/packages/com.termux/\n\n"
    exit 1
fi
ok "Termux detected"

# ── Fix TMPDIR immediately ─────────────────────────────────────────────────────
export TMPDIR="${TMPDIR:-${PREFIX}/tmp}"
mkdir -p "$TMPDIR"
ok "TMPDIR ready"

# ── STEP 1: Update packages ────────────────────────────────────────────────────
printf "\n"
info "Updating package list..."
pkg update -y 2>/dev/null || pkg update 2>/dev/null || true
ok "Packages updated"

# ── STEP 2: Install Python, Git, termux-api ───────────────────────────────────
info "Installing Python, Git, termux-api..."
pkg install -y python git termux-api 2>/dev/null || \
    pkg install -y python git 2>/dev/null || \
    pkg install python git 2>/dev/null || true
ok "Python, Git, termux-api installed"

# ── STEP 3: Install Python packages ───────────────────────────────────────────
info "Installing Python packages..."
pip install --upgrade pip --quiet 2>/dev/null || true
pip install requests colorama --quiet 2>/dev/null || \
    pip install requests colorama 2>/dev/null || true
ok "Packages installed (requests, colorama)"

# ── STEP 4: Clone or update repo ──────────────────────────────────────────────
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

# ── STEP 5: Fix TMPDIR permanently ────────────────────────────────────────────
BASHRC="$HOME/.bashrc"
touch "$BASHRC"
if ! grep -q "TMPDIR" "$BASHRC" 2>/dev/null; then
    printf '\n# Clean Shot\nexport TMPDIR="${PREFIX}/tmp"\n' >> "$BASHRC"
    ok "TMPDIR added to ~/.bashrc"
fi

# ── STEP 6: Create cleanshot launcher ─────────────────────────────────────────
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

# ── Add ~/bin to PATH if needed ────────────────────────────────────────────────
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    printf '\nexport PATH="$HOME/bin:$PATH"\n' >> "$BASHRC"
    ok "~/bin added to PATH"
fi
export PATH="$BIN_DIR:$PATH"

# ── STEP 7: Run doctor ────────────────────────────────────────────────────────
printf "\n"
info "Checking Clean Shot..."
(cd "$INSTALL_DIR/clean-shot" && python3 platforms/android/main.py doctor 2>/dev/null) || true

# ── Success ────────────────────────────────────────────────────────────────────
printf "\n"
printf "${GREEN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
printf "${GREEN}  Clean Shot installed!               ${NC}\n\n"
printf "  Restart Termux then type:\n"
printf "${CYAN}    cleanshot${NC}\n\n"
printf "  For help:  cleanshot help\n"
printf "  Support:   support@cleanshothq.com\n"
printf "${GREEN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n\n"
