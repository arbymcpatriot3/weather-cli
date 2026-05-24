#!/usr/bin/env bash
# File: cleanshot.sh
cd "$(dirname "$0")"

# Platform detection
case "$(uname -s)" in
    Linux)
        # Check for Android (Termux sets $PREFIX)
        if [[ -n "$PREFIX" && "$PREFIX" == *termux* ]]; then
            exec ./clean-shot/platforms/android/cleanshot.sh "$@"
        else
            exec ./clean-shot/platforms/linux/cleanshot.sh "$@"
        fi
        ;;
    Darwin)
        exec ./weather-cli/clean-shot/platforms/macos/cleanshot.sh "$@"
        ;;
    *)
        echo "Unsupported platform!"
        exit 1
        ;;
esac
