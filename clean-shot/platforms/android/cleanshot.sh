#!/usr/bin/env bash
# platforms/android/cleanshot.sh — Run Clean Shot from repo on Android/Termux
#
# Usage:
#   bash platforms/android/cleanshot.sh
#   bash platforms/android/cleanshot.sh watch
#   bash platforms/android/cleanshot.sh help
#
# Or make it executable:
#   chmod +x platforms/android/cleanshot.sh && ./platforms/android/cleanshot.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Termux: ensure TMPDIR is set
export TMPDIR="${TMPDIR:-${PREFIX:-/data/data/com.termux/files/usr}/tmp}"
export CLEANSHOT_CMD=cleanshot

exec python3 "$SCRIPT_DIR/main.py" "$@"
