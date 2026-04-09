#!/usr/bin/env bash
# platforms/linux/install.sh — Clean Shot Linux installer
# Blue Collar Nation LLC

set -e

APP_NAME="clean-shot"
REPO="bluecollarnation/clean-shot"
INSTALL_DIR="$HOME/.local/share/clean-shot"
BIN_DIR="$HOME/.local/bin"
PYTHON_MIN="3.8"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC}  $1"; }
warn() { echo -e "${YELLOW}⚠${NC}  $1"; }
err()  { echo -e "${RED}✗${NC}  $1"; exit 1; }
info() { echo -e "   $1"; }

echo
echo "  Clean Shot — Linux Installer"
echo "  Built for the road, not the boardroom."
echo "  ─────────────────────────────────────────"
echo

# ── Check Python ──────────────────────────────────────────────────────────────
command -v python3 &>/dev/null || err "Python 3 is required but not installed."

PYTHON_OK=$(python3 -c "import sys; print('yes' if sys.version_info >= (3,8) else 'no')")
PYTHON_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
[ "$PYTHON_OK" = "yes" ] || err "Python $PYTHON_MIN or newer required. Found: $PYTHON_VER"
ok "Python $PYTHON_VER found"

# ── Check pip ─────────────────────────────────────────────────────────────────
python3 -m pip --version &>/dev/null || err "pip required. Try: sudo apt install python3-pip"
ok "pip found"

# ── Check curl ────────────────────────────────────────────────────────────────
command -v curl &>/dev/null || err "curl required. Try: sudo apt install curl"

# ── Create directories ────────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR"/{core,display,platforms/linux,claude,tests}
mkdir -p "$BIN_DIR"

# ── Download package files ────────────────────────────────────────────────────
echo
info "Downloading Clean Shot v3.0.0..."

BASE_URL="https://raw.githubusercontent.com/$REPO/main"

CORE_FILES="core/cache.py core/api.py core/parse.py core/config.py core/weather.py
            core/alerts.py core/hazards.py core/dot511.py core/parking.py
            core/hos.py core/health.py core/tts.py core/voice.py
            core/feedback.py core/referral.py core/subscription.py
            core/gps.py core/compress.py"

DISPLAY_FILES="display/full.py display/route.py display/glance.py
               display/dashboard.py display/themes.py"

PLATFORM_FILES="platforms/linux/tts_linux.py platforms/linux/gps_linux.py"

OTHER_FILES="requirements.txt"

for FILE in $CORE_FILES $DISPLAY_FILES $PLATFORM_FILES $OTHER_FILES; do
    mkdir -p "$INSTALL_DIR/$(dirname $FILE)"
    curl -fsSL "$BASE_URL/$FILE" -o "$INSTALL_DIR/$FILE" || warn "Could not download $FILE (skipped)"
    ok "Downloaded $FILE"
done

# ── Init files ────────────────────────────────────────────────────────────────
for PKG in "" core display platforms/linux claude tests; do
    touch "$INSTALL_DIR/$PKG/__init__.py" 2>/dev/null || true
done

# ── Install dependencies ──────────────────────────────────────────────────────
echo
info "Installing Python dependencies..."
python3 -m pip install -r "$INSTALL_DIR/requirements.txt" --quiet --user \
    || python3 -m pip install -r "$INSTALL_DIR/requirements.txt" --quiet --break-system-packages \
    || err "Failed to install dependencies."
ok "Dependencies installed"

# ── Create launcher ───────────────────────────────────────────────────────────
cat > "$BIN_DIR/cleanshot" << EOF
#!/usr/bin/env bash
export CLEANSHOT_CMD=cleanshot
exec python3 "$INSTALL_DIR/platforms/linux/main.py" "\$@"
EOF
chmod +x "$BIN_DIR/cleanshot"
ok "Launcher created at $BIN_DIR/cleanshot"

# ── PATH check ────────────────────────────────────────────────────────────────
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo
    warn "$BIN_DIR is not in your PATH. Add to ~/.bashrc or ~/.zshrc:"
    info '  export PATH="$HOME/.local/bin:$PATH"'
    info "Then reload: source ~/.bashrc"
else
    ok "$BIN_DIR is in your PATH"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo
echo "  ─────────────────────────────────────────"
ok "Clean Shot installed!"
echo
info "Run:  cleanshot"
info "Help: cleanshot help"
echo
