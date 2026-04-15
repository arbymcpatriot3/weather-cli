#!/usr/bin/env sh
# install.sh — Clean Shot: Driver Intelligence System
# Smart platform installer — detects Android, macOS, or Linux and runs the right installer.
# Blue Collar Nation LLC — cleanshothq.com
#
# One-line install:
#   curl -fsSL https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/install.sh | sh

set -e

# Detect script directory (works when run as a file, not piped)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

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
    if [ -f "$SCRIPT_DIR/clean-shot/platforms/android/install_termux.sh" ]; then
        sh "$SCRIPT_DIR/clean-shot/platforms/android/install_termux.sh"
    else
        printf "  Repo not found. Clone the repo first:\n"
        printf "  git clone https://github.com/arbymcpatriot3/weather-cli.git\n\n"
        exit 1
    fi

# ── macOS ─────────────────────────────────────────────────────────────────────
elif [ "$(uname)" = "Darwin" ]; then
    printf "  🍎 Platform: macOS\n\n"
    if [ -f "$SCRIPT_DIR/clean-shot/platforms/macos/install.sh" ]; then
        sh "$SCRIPT_DIR/clean-shot/platforms/macos/install.sh"
    else
        printf "  Repo not found. Clone the repo first:\n"
        printf "  git clone https://github.com/arbymcpatriot3/weather-cli.git\n\n"
        exit 1
    fi

# ── Linux ─────────────────────────────────────────────────────────────────────
else
    printf "  🐧 Platform: Linux\n\n"
    if [ -f "$SCRIPT_DIR/clean-shot/platforms/linux/install.sh" ]; then
        sh "$SCRIPT_DIR/clean-shot/platforms/linux/install.sh"
    else
        printf "  Repo not found. Clone the repo first:\n"
        printf "  git clone https://github.com/arbymcpatriot3/weather-cli.git\n\n"
        exit 1
    fi
fi
