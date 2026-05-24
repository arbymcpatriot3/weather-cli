#!/usr/bin/env python3
# claude/parser.py — Clean Shot: Claude hazard report parser
# Calls Claude API to parse free-text driver reports into structured data.
# Falls back to keyword matching offline.
# TODO: implement API integration in module sprint

from claude.prompts import hazard_parse_prompt


def parse_hazard_report(text: str, api_key: str = None) -> dict:
    """
    Parse a free-text hazard report using Claude.
    Falls back to keyword matching if offline or no API key.
    Returns structured report dict.
    """
    if api_key:
        return _parse_with_claude(text, api_key)
    return _parse_offline(text)


def _parse_with_claude(text: str, api_key: str) -> dict:
    """Call Claude API to parse the report. Stub."""
    # TODO: use anthropic SDK, call claude.prompts.hazard_parse_prompt(text)
    return _parse_offline(text)


def _parse_offline(text: str) -> dict:
    """Keyword-based offline fallback parser."""
    text_lower = text.lower()
    hazard_type = "other"
    if any(w in text_lower for w in ("ice", "icy", "black ice", "slick")):
        hazard_type = "black_ice"
    elif any(w in text_lower for w in ("fog", "foggy", "visibility")):
        hazard_type = "fog"
    elif any(w in text_lower for w in ("flood", "water", "flooded")):
        hazard_type = "flood"
    elif any(w in text_lower for w in ("accident", "crash", "wreck")):
        hazard_type = "accident"
    elif any(w in text_lower for w in ("debris", "stuff in road", "object")):
        hazard_type = "debris"
    elif any(w in text_lower for w in ("construction", "work zone", "cone")):
        hazard_type = "construction"

    return {
        "type":      hazard_type,
        "severity":  "medium",
        "direction": "unknown",
        "cleared":   False,
        "notes":     text[:50],
    }
