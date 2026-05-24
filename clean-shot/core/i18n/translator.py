#!/usr/bin/env python3
# core/i18n/translator.py — Clean Shot: lightweight translation engine
#
# Usage:
#   from core.i18n.translator import t, set_language, detect_language
#
#   t("direction.E")                          → "Eastbound" / "este"
#   t("location.highway_near_city",
#       highway="I-76",
#       direction=t("direction.E"),
#       city="Harrisburg", state="PA")        → "I-76 Eastbound near Harrisburg, PA"
#
# Language auto-detect order:
#   1. config["language"]
#   2. LANG / LANGUAGE env vars
#   3. Python locale
#   4. English fallback (always)
#
# RTL flag: is_rtl() returns True for Arabic, Hebrew, Farsi, Urdu.
# UI rendering for RTL is a future milestone — flag is here now so display
# code can check it without a breaking change later.

import json
import os
import locale
from pathlib import Path

_LOCALE_DIR   = Path(__file__).parent
_SUPPORTED    = {"en", "es"}
_RTL_LANGS    = {"ar", "he", "fa", "ur"}   # future support — flag only for now

_strings: dict = {}          # loaded translation strings
_lang: str     = "en"        # active language code
_en_fallback: dict = {}      # always-loaded English strings


def _load(lang: str) -> dict:
    """Load a language file. Returns {} on failure."""
    path = _LOCALE_DIR / f"{lang}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _bootstrap():
    """Load English as fallback once at import time."""
    global _en_fallback
    if not _en_fallback:
        _en_fallback = _load("en")


def detect_language() -> str:
    """
    Infer best language from environment.
    Returns a supported language code, defaulting to 'en'.
    """
    for source in (
        os.environ.get("LANG",     ""),
        os.environ.get("LANGUAGE", ""),
    ):
        code = source[:2].lower()
        if code in _SUPPORTED:
            return code

    try:
        loc = locale.getdefaultlocale()[0] or ""
        code = loc[:2].lower()
        if code in _SUPPORTED:
            return code
    except Exception:
        pass

    return "en"


def set_language(lang: str) -> None:
    """
    Activate a language.  Falls back to English for unknown codes.
    Call once at startup using config["language"] or detect_language().
    """
    global _lang, _strings
    _bootstrap()
    _lang = lang if lang in _SUPPORTED else "en"
    _strings = _load(_lang) if _lang != "en" else {}


def t(key: str, **kwargs) -> str:
    """
    Translate a dot-notation key with optional {placeholder} interpolation.

    Falls back to English if the key is missing in the active language.
    Falls back to the key itself if missing in both (never crashes).

    Examples:
        t("direction.E")          → "Eastbound"
        t("gps.no_fix")           → "No GPS fix"
        t("hazard.too_far", dist=1.3)
                                  → "Too far from reported location (1.3 mi away)"
    """
    _bootstrap()
    raw = _strings.get(key) or _en_fallback.get(key) or key
    if kwargs:
        try:
            return raw.format(**kwargs)
        except (KeyError, ValueError):
            return raw
    return raw


def current_language() -> str:
    """Return the active language code."""
    return _lang


def is_rtl(lang: str = None) -> bool:
    """
    Return True if the language is right-to-left.
    RTL rendering is not yet implemented — this flag lets display code
    prepare for it without a breaking change.
    """
    return (lang or _lang) in _RTL_LANGS


def supported_languages() -> list:
    """Return list of supported language codes."""
    return sorted(_SUPPORTED)
