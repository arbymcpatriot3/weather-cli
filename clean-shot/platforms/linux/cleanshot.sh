#!/usr/bin/env bash
# platforms/linux/cleanshot.sh — Run Clean Shot directly from the repo
# Use this if you haven't run install.sh yet.
#
# Usage from repo root:
#   bash platforms/linux/cleanshot.sh
#   bash platforms/linux/cleanshot.sh watch
#   bash platforms/linux/cleanshot.sh help
#
# Or make it executable once:
#   chmod +x platforms/linux/cleanshot.sh
#   ./platforms/linux/cleanshot.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CLEANSHOT_CMD=cleanshot
exec python3 "$SCRIPT_DIR/main.py" "$@"
