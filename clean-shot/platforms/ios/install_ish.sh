#!/usr/bin/env sh
# platforms/ios/install_ish.sh — Clean Shot installer for iOS iSH
# Blue Collar Nation LLC — cleanshothq.com
#
# iSH is an Alpine Linux shell emulator for iPhone/iPad.
# App Store: https://apps.apple.com/app/ish-shell/id1436902243
#
# Run inside iSH:
#   wget -qO- https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/clean-shot/platforms/ios/install_ish.sh | sh
#
# Or if you have the repo:
#   sh platforms/ios/install_ish.sh

set -e

INSTALL_DIR="$HOME/.local/share/clean-shot"
BIN_DIR="$HOME/bin"
REPO_URL="https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/clean-shot"

ok()   { echo "✓  $1"; }
warn() { echo "⚠  $1"; }
err()  { echo "✗  $1"; exit 1; }
info() { echo "   $1"; }

echo
echo "  Clean Shot — iSH Installer"
echo "  Built for the road, not the boardroom."
echo "  -----------------------------------------"
echo

# ── Install packages via apk ───────────────────────────────────────────────────
info "Updating apk..."
apk update -q 2>/dev/null || warn "apk update failed — continuing anyway"

info "Installing python3..."
apk add --quiet python3 py3-pip curl wget 2>/dev/null || \
    err "Failed to install python3. Make sure you have network access in iSH."
ok "Python3 installed"

# ── Install Python dependencies ────────────────────────────────────────────────
pip3 install --quiet requests colorama || \
    err "Failed to install Python deps. Try: pip3 install requests colorama"
ok "Python dependencies installed"

# ── TMPDIR ────────────────────────────────────────────────────────────────────
export TMPDIR="${TMPDIR:-/tmp}"
mkdir -p "$TMPDIR"
ok "TMPDIR set to $TMPDIR"

# ── Create install directory ───────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/core/i18n"
mkdir -p "$INSTALL_DIR/display"
mkdir -p "$INSTALL_DIR/platforms/ios"
mkdir -p "$INSTALL_DIR/claude"
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

IOS_FILES="platforms/__init__.py platforms/ios/__init__.py platforms/ios/main.py"

OTHER_FILES="requirements.txt claude/__init__.py claude/prompts.py claude/parser.py"

for FILE in $CORE_FILES $DISPLAY_FILES $IOS_FILES $OTHER_FILES; do
    mkdir -p "$INSTALL_DIR/$(dirname $FILE)"
    if wget -qO "$INSTALL_DIR/$FILE" "$REPO_URL/$FILE" 2>/dev/null; then
        ok "Downloaded $FILE"
    else
        warn "Could not download $FILE (skipped)"
    fi
done

# ── Create launcher ────────────────────────────────────────────────────────────
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/cleanshot" << LAUNCHER
#!/usr/bin/env sh
export CLEANSHOT_CMD=cleanshot
exec python3 "$INSTALL_DIR/platforms/ios/main.py" "\$@"
LAUNCHER
chmod +x "$BIN_DIR/cleanshot"
ok "Launcher created at $BIN_DIR/cleanshot"

# ── Add ~/bin to PATH and TMPDIR to ~/.profile ────────────────────────────────
PROFILE="$HOME/.profile"
touch "$PROFILE"

if ! grep -q 'PATH.*HOME/bin' "$PROFILE" 2>/dev/null; then
    printf '\n# Clean Shot\nexport PATH="$HOME/bin:$PATH"\n' >> "$PROFILE"
    ok "~/bin added to PATH in ~/.profile"
fi

if ! grep -q "TMPDIR" "$PROFILE" 2>/dev/null; then
    echo 'export TMPDIR="${TMPDIR:-/tmp}"' >> "$PROFILE"
    ok "TMPDIR added to ~/.profile"
fi

# ── Done ───────────────────────────────────────────────────────────────────────
echo
echo "  -----------------------------------------"
ok "Clean Shot installed!"
echo
info "Reload your profile: . ~/.profile"
info "Then: cleanshot"
info "Help: cleanshot help"
info "Check: cleanshot doctor"
echo
