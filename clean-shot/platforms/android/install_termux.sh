#!/usr/bin/env bash
# platforms/android/install_termux.sh — Clean Shot installer for Android/Termux
# Blue Collar Nation LLC — cleanshothq.com
#
# Run from Termux:
#   curl -fsSL https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/clean-shot/platforms/android/install_termux.sh | bash
#
# Or if you already have the repo cloned:
#   bash platforms/android/install_termux.sh

set -e

APP_NAME="clean-shot"
INSTALL_DIR="$HOME/.local/share/clean-shot"
BIN_DIR="$HOME/bin"
REPO_URL="https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/clean-shot"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC}  $1"; }
warn() { echo -e "${YELLOW}⚠${NC}  $1"; }
err()  { echo -e "${RED}✗${NC}  $1"; exit 1; }
info() { echo    "   $1"; }

echo
echo "  Clean Shot — Termux Installer"
echo "  Built for the road, not the boardroom."
echo "  ─────────────────────────────────────────"
echo

# ── Verify we're in Termux ─────────────────────────────────────────────────────
if [ -z "$PREFIX" ] || [ ! -d "$PREFIX/bin" ]; then
    err "This installer is for Termux on Android. PREFIX not found."
fi
ok "Termux environment detected"

# ── Ensure TMPDIR is set ───────────────────────────────────────────────────────
export TMPDIR="${TMPDIR:-$PREFIX/tmp}"
mkdir -p "$TMPDIR"
ok "TMPDIR set to $TMPDIR"

# ── Install system packages ────────────────────────────────────────────────────
echo
info "Installing packages via pkg..."
pkg update -y -q 2>/dev/null || true
pkg install -y python termux-api curl 2>/dev/null || \
    err "Failed to install packages. Try: pkg update && pkg install python termux-api"
ok "Python and termux-api installed"

# ── Install Python dependencies ────────────────────────────────────────────────
pip install --quiet requests colorama || \
    err "Failed to install Python deps. Try: pip install requests colorama"
ok "Python dependencies installed"

# ── Create install directory ───────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR"/{core,display,platforms/android,claude,tests}
mkdir -p "$INSTALL_DIR/core/i18n"
mkdir -p "$BIN_DIR"

# ── Download package files ─────────────────────────────────────────────────────
echo
info "Downloading Clean Shot..."

CORE_FILES="core/__init__.py core/cache.py core/api.py core/parse.py core/config.py
            core/weather.py core/alerts.py core/hazards.py core/dot511.py
            core/parking.py core/hos.py core/tts.py core/gps.py
            core/subscription.py core/referral.py core/compress.py
            core/feedback.py core/health.py core/voice.py
            core/i18n/__init__.py core/i18n/translator.py
            core/i18n/en.json core/i18n/es.json"

DISPLAY_FILES="display/__init__.py display/full.py display/route.py
               display/display_alerts.py display/glance.py
               display/dashboard.py display/themes.py"

ANDROID_FILES="platforms/__init__.py platforms/android/__init__.py
               platforms/android/main.py"

OTHER_FILES="requirements.txt claude/__init__.py claude/prompts.py claude/parser.py"

for FILE in $CORE_FILES $DISPLAY_FILES $ANDROID_FILES $OTHER_FILES; do
    mkdir -p "$INSTALL_DIR/$(dirname $FILE)"
    if curl -fsSL "$REPO_URL/$FILE" -o "$INSTALL_DIR/$FILE" 2>/dev/null; then
        ok "Downloaded $FILE"
    else
        warn "Could not download $FILE (skipped)"
    fi
done

# ── Create launcher ────────────────────────────────────────────────────────────
cat > "$BIN_DIR/cleanshot" << LAUNCHER
#!/usr/bin/env bash
export TMPDIR="\${TMPDIR:-\${PREFIX:-/data/data/com.termux/files/usr}/tmp}"
export CLEANSHOT_CMD=cleanshot
exec python3 "$INSTALL_DIR/platforms/android/main.py" "\$@"
LAUNCHER
chmod +x "$BIN_DIR/cleanshot"
ok "Launcher created at $BIN_DIR/cleanshot"

# ── Add ~/bin to PATH if needed ────────────────────────────────────────────────
BASHRC="$HOME/.bashrc"
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo '' >> "$BASHRC"
    echo '# Clean Shot' >> "$BASHRC"
    echo 'export PATH="$HOME/bin:$PATH"' >> "$BASHRC"
    warn "$BIN_DIR added to PATH in ~/.bashrc"
    info "Run: source ~/.bashrc  (or restart Termux)"
else
    ok "$BIN_DIR is already in PATH"
fi

# ── Add TMPDIR to .bashrc if not already set ──────────────────────────────────
if ! grep -q "TMPDIR" "$BASHRC" 2>/dev/null; then
    echo 'export TMPDIR="$PREFIX/tmp"' >> "$BASHRC"
    ok "TMPDIR added to ~/.bashrc"
fi

# ── Done ───────────────────────────────────────────────────────────────────────
echo
echo "  ─────────────────────────────────────────"
ok "Clean Shot installed!"
echo
info "Restart Termux or run: source ~/.bashrc"
info "Then: cleanshot"
info "Help: cleanshot help"
info "Check: cleanshot doctor"
echo
