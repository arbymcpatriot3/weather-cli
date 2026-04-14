#!/usr/bin/env bash
# install.sh — Clean Shot: Driver Intelligence System
# Smart platform installer — detects Android, macOS, or Linux and runs the right installer.
# Blue Collar Nation LLC — cleanshothq.com
#
# One-line install:
#   curl -fsSL https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/install.sh | bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

printf "\n"
printf "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
printf "  🚛 CLEAN SHOT\n"
printf "     Driver Intelligence System\n"
printf "     By Blue Collar Nation LLC\n"
printf "     cleanshothq.com\n"
printf "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

printf "  Detecting your platform...\n\n"

# ── Android / Termux ──────────────────────────────────────────────────────────
if [ -n "${TERMUX_VERSION:-}" ] || ([ -n "${PREFIX:-}" ] && echo "$PREFIX" | grep -q "com.termux"); then
    printf "  📱 Platform: Android (Termux)\n\n"
    bash "$SCRIPT_DIR/clean-shot/platforms/android/install_termux.sh"

# ── macOS ─────────────────────────────────────────────────────────────────────
elif [ "$(uname)" = "Darwin" ]; then
    printf "  🍎 Platform: macOS\n\n"
    bash "$SCRIPT_DIR/clean-shot/platforms/macos/install.sh"

# ── Linux ─────────────────────────────────────────────────────────────────────
else
    printf "  🐧 Platform: Linux\n\n"
    bash "$SCRIPT_DIR/clean-shot/platforms/linux/install.sh"
fi
