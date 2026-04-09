#!/usr/bin/env sh
# platforms/ios/install_ish.sh — Clean Shot iOS iSH Installer
# Blue Collar Nation LLC — cleanshothq.com
#
# iSH is a free Alpine Linux shell for iPhone/iPad (App Store).
#
# One-line install inside iSH:
#   curl -fsSL https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/clean-shot/platforms/ios/install_ish.sh | sh

# Note: iSH uses /bin/sh (ash), not bash. No pipefail, no [[ ]].
set -eu

INSTALL_DIR="$HOME/CleanShot"
BIN_DIR="$HOME/bin"
REPO_URL="https://github.com/arbymcpatriot3/weather-cli.git"

ok()   { printf "  [OK]  %s\n" "$1"; }
warn() { printf "  [!]   %s\n" "$1"; }
info() { printf "        %s\n" "$1"; }
die()  {
    printf "\n  [ERR] %s\n\n" "$1"
    printf "  Need help? support@cleanshothq.com\n"
    printf "  cleanshothq.com\n\n"
    exit 1
}

# ── Header ─────────────────────────────────────────────────────────────────────
printf "\n"
printf "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
printf "  Clean Shot — iOS iSH Installer     \n"
printf "  Built for the road, not the boardroom\n"
printf "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

# ── Verify iSH / Alpine environment ───────────────────────────────────────────
if ! command -v apk > /dev/null 2>&1; then
    die "This installer is for iSH on iOS (Alpine Linux). Install iSH from the App Store."
fi
ok "iSH environment detected"

# ── Fix TMPDIR immediately ─────────────────────────────────────────────────────
TMPDIR="${TMPDIR:-/tmp}"
mkdir -p "$TMPDIR"
export TMPDIR
ok "TMPDIR: $TMPDIR"

# ── STEP 1: Install packages ───────────────────────────────────────────────────
printf "\n"
info "Updating package list..."
apk update -q 2>/dev/null || warn "apk update had warnings — continuing"

info "Installing Python, Git, curl..."
apk add --quiet python3 py3-pip git curl wget 2>/dev/null || \
    die "Package install failed. Make sure you have network access in iSH (Settings → Allow Network)."
ok "Python3, Git, curl installed"

# ── STEP 2: Install Python packages ───────────────────────────────────────────
info "Installing Python packages..."
pip3 install requests colorama --quiet 2>/dev/null || \
    pip3 install requests colorama --quiet --break-system-packages 2>/dev/null || \
    warn "Package install had issues. Run: pip3 install requests colorama"
ok "Packages installed (requests, colorama)"

# ── STEP 3: Clone or update repo ──────────────────────────────────────────────
printf "\n"
info "Setting up Clean Shot..."
if [ -f "$INSTALL_DIR/clean-shot/platforms/ios/main.py" ]; then
    info "Updating existing installation..."
    git -C "$INSTALL_DIR" pull --quiet 2>/dev/null || warn "Could not update — using existing version"
    ok "Updated to latest version"
else
    info "Downloading Clean Shot (about 30 seconds on iSH)..."
    [ -d "$INSTALL_DIR" ] && rm -rf "$INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR" --quiet 2>/dev/null || \
        git clone "$REPO_URL" "$INSTALL_DIR" 2>&1 | tail -1 || true
    [ -f "$INSTALL_DIR/clean-shot/platforms/ios/main.py" ] || \
        die "Download failed. Check your internet connection and try again."
    ok "Clean Shot downloaded to: $INSTALL_DIR"
fi

# ── STEP 4: Fix TMPDIR permanently ────────────────────────────────────────────
PROFILE="$HOME/.profile"
touch "$PROFILE"
if ! grep -q "TMPDIR" "$PROFILE" 2>/dev/null; then
    printf '\n# Clean Shot\nexport TMPDIR="${TMPDIR:-/tmp}"\n' >> "$PROFILE"
    ok "TMPDIR added to ~/.profile"
fi

# ── STEP 5: Create cleanshot launcher ─────────────────────────────────────────
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/cleanshot" << 'LAUNCHER'
#!/usr/bin/env sh
export TMPDIR="${TMPDIR:-/tmp}"
export CLEANSHOT_CMD=cleanshot
cd "$HOME/CleanShot/clean-shot"
exec python3 platforms/ios/main.py "$@"
LAUNCHER
chmod +x "$BIN_DIR/cleanshot"
ok "Launcher: $BIN_DIR/cleanshot"

# ── Add ~/bin to PATH if needed ────────────────────────────────────────────────
if ! echo "$PATH" | grep -q "$BIN_DIR" 2>/dev/null; then
    printf '\nexport PATH="$HOME/bin:$PATH"\n' >> "$PROFILE"
    ok "~/bin added to PATH in ~/.profile"
fi

# ── STEP 6: Run doctor ────────────────────────────────────────────────────────
printf "\n"
info "Running system check..."
export PATH="$BIN_DIR:$PATH"
(cd "$INSTALL_DIR/clean-shot" && python3 platforms/ios/main.py doctor 2>/dev/null) || \
    warn "System check had warnings — run 'cleanshot doctor' after restarting iSH"

# ── Success ────────────────────────────────────────────────────────────────────
printf "\n"
printf "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
printf "  OK  Clean Shot installed!\n\n"
printf "  Reload profile then type:\n"
printf "    . ~/.profile && cleanshot\n\n"
printf "  For help:      cleanshot help\n"
printf "  Check system:  cleanshot doctor\n\n"
printf "  Need help?     support@cleanshothq.com\n"
printf "                 cleanshothq.com\n"
printf "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
