#!/usr/bin/env bash
# install.sh - Weather CLI installer
# https://github.com/arbymcpatriot3/weather-cli

set -e

REPO="arbymcpatriot3/weather-cli"
INSTALL_DIR="$HOME/.local/share/weather-cli"
BIN_DIR="$HOME/.local/bin"
PYTHON_MIN="3.8"

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ok()   { echo -e "${GREEN}✓${NC}  $1"; }
warn() { echo -e "${YELLOW}⚠${NC}  $1"; }
err()  { echo -e "${RED}✗${NC}  $1"; exit 1; }
info() { echo -e "   $1"; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo
echo "  Weather CLI — Installer"
echo "  https://github.com/$REPO"
echo "  ─────────────────────────────────────"
echo

# ── Check Python ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    err "Python 3 is required but not installed."
fi

PYTHON_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_OK=$(python3 -c "import sys; print('yes' if sys.version_info >= (3,8) else 'no')")

if [ "$PYTHON_OK" != "yes" ]; then
    err "Python $PYTHON_MIN or newer required. Found: $PYTHON_VER"
fi
ok "Python $PYTHON_VER found"

# ── Check pip ─────────────────────────────────────────────────────────────────
if ! python3 -m pip --version &>/dev/null; then
    err "pip is required but not installed. Try: sudo apt install python3-pip"
fi
ok "pip found"

# ── Check curl ────────────────────────────────────────────────────────────────
if ! command -v curl &>/dev/null; then
    err "curl is required. Try: sudo apt install curl"
fi

# ── Create directories ────────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"

# ── Download files ────────────────────────────────────────────────────────────
echo
info "Downloading Weather CLI v2.0.0..."

BASE_URL="https://raw.githubusercontent.com/$REPO/main"

FILES="weather.py api.py config.py parse.py display.py requirements.txt"

for FILE in $FILES; do
    curl -fsSL "$BASE_URL/$FILE" -o "$INSTALL_DIR/$FILE" || err "Failed to download $FILE"
    ok "Downloaded $FILE"
done

# ── Install dependencies ──────────────────────────────────────────────────────
echo
info "Installing Python dependencies..."

python3 -m pip install -r "$INSTALL_DIR/requirements.txt" --quiet --user \
    || python3 -m pip install -r "$INSTALL_DIR/requirements.txt" --quiet --break-system-packages \
    || err "Failed to install dependencies. Try manually: pip3 install requests colorama"

ok "Dependencies installed"

# ── Create launcher script ────────────────────────────────────────────────────
cat > "$BIN_DIR/weather" << EOF
#!/usr/bin/env bash
exec python3 "$INSTALL_DIR/weather.py" "\$@"
EOF

chmod +x "$BIN_DIR/weather"
ok "Launcher created at $BIN_DIR/weather"

# ── Add ~/.local/bin to PATH if needed ───────────────────────────────────────
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo
    warn "$BIN_DIR is not in your PATH."
    info "Add this to your ~/.bashrc or ~/.zshrc:"
    info ""
    info "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    info ""
    info "Then reload your shell: source ~/.bashrc"
    info "Or run now with: python3 $INSTALL_DIR/weather.py"
else
    ok "$BIN_DIR is in your PATH"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo
echo "  ─────────────────────────────────────"
ok "Weather CLI installed successfully!"
echo
info "Run:  weather"
info "Help: weather help"
info "Example: weather \"Pennsville NJ\""
echo
