#!/usr/bin/env python3
# tests/test_hazards.py — Clean Shot: hazard module tests
# TODO: implement tests alongside core/hazards.py and claude/parser.py

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claude.parser import _parse_offline


def test_offline_parser_black_ice():
    result = _parse_offline("black ice on the interstate")
    assert result["type"] == "black_ice", f"Got {result['type']}"
    print("✓ offline parser: black_ice")


def test_offline_parser_fog():
    result = _parse_offline("heavy fog, can't see a thing")
    assert result["type"] == "fog"
    print("✓ offline parser: fog")


def test_offline_parser_fallback():
    result = _parse_offline("something weird on the road")
    assert result["type"] == "other"
    print("✓ offline parser: fallback to other")


if __name__ == "__main__":
    test_offline_parser_black_ice()
    test_offline_parser_fog()
    test_offline_parser_fallback()
    print("All hazard tests passed.")
