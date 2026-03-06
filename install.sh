#!/usr/bin/env bash

set -e

REPO="arbymcpatriot3/weather-cli"

echo "Installing Weather CLI..."

LATEST=$(curl -s https://api.github.com/repos/$REPO/releases/latest | jq -r ".tag_name")

FILE="weather-cli_${LATEST#v}_all.deb"

URL="https://github.com/$REPO/releases/download/$LATEST/$FILE"

TMP=$(mktemp -d)

cd "$TMP"

echo "Downloading $FILE..."

curl -LO "$URL"

echo "Installing..."

sudo apt install -y ./$FILE

echo
echo "Weather CLI installed!"
echo
echo "Run:"
echo "weather"

