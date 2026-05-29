#!/usr/bin/env python3
# core/referral.py — Clean Shot: referral engine
# Blue Collar Nation LLC
#
# Referral economics:
#   Each referral = 10% off your subscription forever
#   10 referrals   = free subscription
#   11+ referrals  = we pay YOU monthly (ambassador dividend)
#
# Referral tiers by count:
#   0-1   Road Scout
#   2-4   Captain
#   5-9   Commander
#   10-14 Legend
#   15-24 Elite
#   25+   Ambassador
#
# Discount is applied server-side; local config caches last known values.
# TODO: implement backend integration in module sprint

import sys
from pathlib import Path


TIERS = [
    (0,  "Road Scout"),
    (2,  "Captain"),
    (5,  "Commander"),
    (10, "Legend"),
    (15, "Elite"),
    (25, "Ambassador"),
]

REFERRAL_DISCOUNT_PCT  = 10   # % off per referral
FREE_AT_REFERRALS      = 10
AMBASSADOR_DIVIDEND    = True  # 11+ referrals = paid monthly


def get_tier(referral_count: int) -> str:
    """Return the referral tier name for a given count."""
    tier = "Road Scout"
    for min_count, name in TIERS:
        if referral_count >= min_count:
            tier = name
    return tier


def calc_discount_pct(referral_count: int) -> float:
    """
    Calculate total discount percentage.
    Capped at 100% (free) for 10+ referrals.
    """
    return min(referral_count * REFERRAL_DISCOUNT_PCT, 100.0)


def is_free_tier(referral_count: int) -> bool:
    return referral_count >= FREE_AT_REFERRALS


def is_ambassador(referral_count: int) -> bool:
    return referral_count > FREE_AT_REFERRALS


def get_referral_link(config: dict) -> str:
    """Return the driver's personal referral link. Stub."""
    driver_id = config.get("driver_id", "")
    ref_code  = config.get("referral_code", "")
    if not ref_code:
        return "Run setup to get your referral link."
    # TODO: return actual link once backend is live
    return f"https://cleanshot.app/r/{ref_code}"


def get_referral_stats(config: dict) -> dict:
    """
    Fetch referral stats from server and update local config cache.
    Returns stats dict. Stub.
    """
    count = config.get("referral_count", 0)
    return {
        "count":        count,
        "tier":         get_tier(count),
        "discount_pct": calc_discount_pct(count),
        "is_free":      is_free_tier(count),
        "is_ambassador":is_ambassador(count),
        "link":         get_referral_link(config),
    }


def capture_referral_code(config: dict) -> str | None:
    """
    Detect a referral code from the current launch and save it to config.

    Sources checked in order:
    1. --ref=CODE on the command line (e.g. from TikTok link: cleanshot --ref=chris42)
    2. install.ref file next to the entry-point script (written by the installer)

    Returns the captured code, or None if none found.
    The code is stored in config["referral_code"] and saved by the caller.
    """
    if config.get("referral_code"):
        return config["referral_code"]   # already captured

    code: str | None = None

    # 1. Check --ref= flag in sys.argv
    for arg in sys.argv[1:]:
        if arg.startswith("--ref="):
            candidate = arg[6:].strip()
            if candidate:
                code = candidate
                break

    # 2. Check install.ref file (written by installer or link handler)
    if not code:
        # Look for install.ref next to the running script, then in clean-shot root
        candidates = [
            Path(sys.argv[0]).resolve().parent / "install.ref",
            Path(__file__).resolve().parent.parent / "install.ref",
        ]
        for ref_file in candidates:
            try:
                if ref_file.exists():
                    candidate = ref_file.read_text().strip()
                    if candidate:
                        code = candidate
                        break
            except Exception:
                pass

    if code:
        config["referral_code"] = code

    return code


def display_referral_card(config: dict) -> None:
    """Print ASCII referral stats card (shareable on social media). Stub."""
    stats = get_referral_stats(config)
    print()
    print("┌─────────────────────────────────────┐")
    print("│  Clean Shot  —  Referral Stats       │")
    print("├─────────────────────────────────────┤")
    print(f"│  Tier     : {stats['tier']:<25}│")
    print(f"│  Referrals: {stats['count']:<25}│")
    print(f"│  Discount : {stats['discount_pct']:.0f}% off forever{' '*(14 - len(str(int(stats['discount_pct']))))}│")
    print(f"│  Link     : {stats['link'][:25]:<25}│")
    print("└─────────────────────────────────────┘")
    print()
