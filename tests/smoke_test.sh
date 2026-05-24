#!/usr/bin/env sh
# tests/smoke_test.sh — Clean Shot smoke test
# Verifies the core install path works: one command, no TTS, compact view, ZIP input.
#
# Run from repo root:
#   sh tests/smoke_test.sh
#
# Exit 0 = pass, exit 1 = fail.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLEAN_SHOT="$REPO_ROOT/clean-shot"

printf "\nRunning Clean Shot smoke test...\n"

# ── Locate Python ──────────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python3.11 python3.10 python3.9 python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    printf "FAIL: Python not found\n"
    exit 1
fi

# ── Verify required packages ───────────────────────────────────────────────────
for pkg in requests colorama; do
    if ! "$PYTHON" -c "import $pkg" >/dev/null 2>&1; then
        printf "FAIL: Python package '%s' not installed\n" "$pkg"
        printf "      Fix: pip3 install %s\n" "$pkg"
        exit 1
    fi
done

# ── Run compact weather check for ZIP 08079 with TTS disabled ─────────────────
printf "  Testing: cleanshot --zip 08079 --no-tts --compact\n"

cd "$CLEAN_SHOT"
CLEANSHOT_CMD=cleanshot \
    "$PYTHON" platforms/linux/main.py --zip 08079 --no-tts --compact || {
    printf "FAIL: cleanshot --zip 08079 --no-tts --compact returned non-zero\n"
    exit 1
}

printf "\n✅ Smoke test passed\n\n"
