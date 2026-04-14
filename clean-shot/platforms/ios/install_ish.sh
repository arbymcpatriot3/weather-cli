#!/usr/bin/env sh
# platforms/ios/install_ish.sh — Clean Shot iOS iSH Installer
# Blue Collar Nation LLC — cleanshothq.com
#
# iSH is a free Alpine Linux shell for iPhone/iPad (App Store).
#
# One-line install inside iSH:
#   curl -fsSL https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/clean-shot/platforms/ios/install_ish.sh | sh

# Note: iSH uses /bin/sh (ash), not bash. No pipefail, no [[ ]].
set -e

INSTALL_DIR="$HOME/CleanShot"
BIN_DIR="$HOME/bin"
REPO_URL="https://github.com/arbymcpatriot3/weather-cli.git"

ok()   { printf "  [OK]  %s\n" "$1"; }
warn() { printf "  [!]   %s\n" "$1"; }
info() { printf "        %s\n" "$1"; }

# ── Header ─────────────────────────────────────────────────────────────────────
printf "\n"
printf "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
printf "  Clean Shot — iOS iSH Installer     \n"
printf "  Built for the road, not the boardroom\n"
printf "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

# ── Verify iSH / Alpine environment ───────────────────────────────────────────
if ! command -v apk > /dev/null 2>&1; then
    printf "\n  This installer runs inside iSH.\n"
    printf "  Download iSH free from the App Store.\n\n"
    exit 1
fi
ok "iSH detected"

# ── Fix TMPDIR immediately ─────────────────────────────────────────────────────
TMPDIR="${TMPDIR:-/tmp}"
mkdir -p "$TMPDIR"
export TMPDIR
ok "TMPDIR ready"

# ── STEP 1: Install packages ───────────────────────────────────────────────────
printf "\n"
info "Updating package list..."
apk update 2>/dev/null || true

info "Installing Python, Git, curl, espeak..."
apk add --quiet python3 py3-pip git curl wget espeak 2>/dev/null || \
    apk add --quiet python3 py3-pip git curl espeak 2>/dev/null || \
    apk add python3 py3-pip git curl 2>/dev/null || \
    apk add python3 git curl 2>/dev/null || true
ok "Python, Git, curl installed"

if command -v espeak > /dev/null 2>&1; then
    ok "espeak installed (TTS engine)"
else
    warn "espeak not installed — voice alerts may be limited"
fi

# ── STEP 2: Install Python packages ───────────────────────────────────────────
info "Installing Python packages (requests, colorama)..."
pip3 install --upgrade pip --quiet 2>/dev/null || true
pip3 install requests colorama --quiet 2>/dev/null || \
    pip3 install requests colorama --quiet --break-system-packages 2>/dev/null || \
    pip3 install requests colorama 2>/dev/null || true
ok "requests, colorama installed"

info "Installing pyttsx3 (voice alerts)..."
pip3 install pyttsx3 --quiet 2>/dev/null || \
    pip3 install pyttsx3 --quiet --break-system-packages 2>/dev/null || \
    pip3 install pyttsx3 2>/dev/null || true
if python3 -c "import pyttsx3" 2>/dev/null; then
    ok "pyttsx3 installed — voice alerts ready"
else
    warn "pyttsx3 not available — voice alerts will use text fallback"
fi

# ── STEP 3: Clone or update repo ──────────────────────────────────────────────
printf "\n"
info "Setting up Clean Shot..."
if [ -d "$INSTALL_DIR/.git" ]; then
    info "Updating existing installation..."
    git -C "$INSTALL_DIR" pull --quiet 2>/dev/null || true
    ok "Updated to latest version"
else
    info "Downloading Clean Shot (about 30 seconds on iSH)..."
    [ -d "$INSTALL_DIR" ] && rm -rf "$INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR" --quiet
    ok "Clean Shot downloaded"
fi

# ── STEP 4: Fix TMPDIR permanently ────────────────────────────────────────────
PROFILE="$HOME/.profile"
touch "$PROFILE"
if ! grep -q "TMPDIR" "$PROFILE" 2>/dev/null; then
    printf '\n# Clean Shot\nexport TMPDIR="${TMPDIR:-/tmp}"\n' >> "$PROFILE"
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

# ── Add ~/bin to PATH ──────────────────────────────────────────────────────────
if ! echo "$PATH" | grep -q "$BIN_DIR" 2>/dev/null; then
    printf '\nexport PATH="$HOME/bin:$PATH"\n' >> "$PROFILE"
    ok "~/bin added to PATH"
fi
# Activate now so doctor works
export PATH="$BIN_DIR:$PATH"

# ── Source profile so changes take effect in this session ─────────────────────
. "$PROFILE" 2>/dev/null || true

# ── STEP 6: Run doctor ────────────────────────────────────────────────────────
printf "\n"
info "Checking Clean Shot..."
(cd "$INSTALL_DIR/clean-shot" && python3 platforms/ios/main.py doctor 2>/dev/null) || true

# ── Success ────────────────────────────────────────────────────────────────────
printf "\n"
printf "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
printf "  Clean Shot installed!\n\n"
printf "  For help:  cleanshot help\n"
printf "  Support:   support@cleanshothq.com\n"
printf "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

# ── Launch Clean Shot ──────────────────────────────────────────────────────────
printf "  Starting Clean Shot...\n\n"
if command -v cleanshot > /dev/null 2>&1; then
    cleanshot
else
    cd "$INSTALL_DIR/clean-shot" && python3 platforms/ios/main.py
fi
