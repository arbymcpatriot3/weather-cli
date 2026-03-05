#!/usr/bin/env bash

set -e

echo "Installing weather-cli..."

TMP_DIR=$(mktemp -d)
cd "$TMP_DIR"

echo "Downloading package..."
curl -L -o weather-cli.deb \
https://github.com/arbymcpatriot3/weather-cli/releases/latest/download/weather-cli.deb

echo "Installing package..."
sudo dpkg -i weather-cli.deb

echo ""
echo "Installation complete."
echo "Run it with:"
echo ""
echo "    weather"
echo ""
