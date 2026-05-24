#!/usr/bin/env sh
# platforms/ios/cleanshot.sh — Run Clean Shot from repo on iOS (iSH)
#
# iSH uses Alpine Linux with /bin/sh (not bash).
# Usage:
#   sh platforms/ios/cleanshot.sh
#   sh platforms/ios/cleanshot.sh watch
#   sh platforms/ios/cleanshot.sh help

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export CLEANSHOT_CMD=cleanshot
exec python3 "$SCRIPT_DIR/main.py" "$@"
