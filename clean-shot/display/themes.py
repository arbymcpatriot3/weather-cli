#!/usr/bin/env python3
# display/themes.py — Clean Shot: display themes
# Affects color palette and ASCII border style only.
# Never affects data or layout — purely cosmetic.
#
# Built-in themes:
#   default    — standard colorama colors
#   nighthawk  — red/amber only (preserves night vision)
#   highvis    — max contrast, bold everything
#   minimal    — no colors, no borders (best for logging/piping)
#   cb         — CB radio aesthetic, amber on black
#
# TODO: implement theme switching in module sprint

from colorama import Fore, Back, Style

THEMES = {
    "default":   {"name": "Default"},
    "nighthawk": {"name": "Nighthawk (night vision safe)"},
    "highvis":   {"name": "High Visibility"},
    "minimal":   {"name": "Minimal (no color)"},
    "cb":        {"name": "CB Radio"},
}


def get_theme(config: dict) -> dict:
    """Return the active theme dict from config."""
    theme_key = config.get("theme", "default")
    return THEMES.get(theme_key, THEMES["default"])


def apply_theme(config: dict):
    """Apply theme settings globally. Stub."""
    # TODO: patch colorama globals or pass theme context to display functions
    pass


def list_themes() -> None:
    """Print available themes."""
    print("Available themes:")
    for key, t in THEMES.items():
        print(f"  {key:<12} — {t['name']}")
    print()
    print("Set with:  cleanshot settings theme nighthawk")
