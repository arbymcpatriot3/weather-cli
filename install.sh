#!/usr/bin/env bash

set -e

REPO="arbymcpatriot3/weather-cli"
LATEST=$(curl -s https://api.github.com/repos/$REPO/releases/latest | jq -r ".tag_name")

DEB="weather-cli_${LATEST#v}_all.deb"

echo
echo "Weather CLI Installer"
echo "Downloading version $LATEST"
echo

URL="https://github.com/$REPO/releases/download/$LATEST/$DEB"

TMP=$(mktemp -d)

cd "$TMP"

echo "Downloading package..."
curl -LO "$URL"

echo "Installing..."

if command -v apt >/dev/null; then
    sudo apt install -y ./$DEB
else
    echo "APT not found. Installing manually."
    sudo dpkg -i $DEB
fi

echo
echo "Weather CLI installed!"
echo
echo "Run:"
echo
echo "weather"
echo
