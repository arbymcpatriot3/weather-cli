#!/usr/bin/env python3
# core/subscription.py — Clean Shot: tier management + feature gating
# Blue Collar Nation LLC
#
# Tiers:
#   free        Basic weather + NOAA alerts. Always available.
#   solo_pro    $19.99/mo — all features (road alerts, parking, HOS, TTS, voice)
#   pro_plus    $29.99/mo — extended (fleet view, API access, white-label)
#   fleet       $15/seat/mo — dashboard + dispatch integration
#   enterprise  custom pricing
#
# Feature gating is checked locally against config["subscription_tier"].
# Server validates on sync; offline mode respects last known tier.
# TODO: billing integration in module sprint


TIERS = {
    "free":       {"price_monthly": 0,     "label": "Free"},
    "solo_pro":   {"price_monthly": 19.99, "label": "Solo Pro"},
    "pro_plus":   {"price_monthly": 29.99, "label": "Pro Plus"},
    "fleet":      {"price_monthly": 15.00, "label": "Fleet (per seat)"},
    "enterprise": {"price_monthly": None,  "label": "Enterprise"},
}

# Features available by minimum tier
_FEATURE_TIER = {
    "basic_weather":    "free",
    "noaa_alerts":      "free",
    "road_alerts":      "solo_pro",
    "community_hazards":"solo_pro",
    "dot511":           "solo_pro",
    "smart_parking":    "solo_pro",
    "hos_guardian":     "solo_pro",
    "wellness":         "solo_pro",
    "tts":              "solo_pro",
    "voice":            "solo_pro",
    "route_weather":    "free",
    "fleet_dashboard":  "fleet",
    "api_access":       "pro_plus",
    "white_label":      "enterprise",
}

_TIER_ORDER = ["free", "solo_pro", "pro_plus", "fleet", "enterprise"]


def has_feature(config: dict, feature: str) -> bool:
    """Return True if config's subscription tier includes the feature."""
    tier         = config.get("subscription_tier", "free")
    required     = _FEATURE_TIER.get(feature, "enterprise")

    # Referral-based free subscription counts as solo_pro
    ref_count = config.get("referral_count", 0)
    if ref_count >= 10 and tier == "free":
        tier = "solo_pro"

    try:
        return _TIER_ORDER.index(tier) >= _TIER_ORDER.index(required)
    except ValueError:
        return False


def get_upgrade_message(feature: str) -> str:
    """Return a terse upgrade prompt for a gated feature."""
    required = _FEATURE_TIER.get(feature, "solo_pro")
    label    = TIERS.get(required, {}).get("label", "Solo Pro")
    return f"⚡ {label} feature — upgrade at cleanshot.app"


def get_tier_label(config: dict) -> str:
    tier = config.get("subscription_tier", "free")
    return TIERS.get(tier, {}).get("label", tier.replace("_", " ").title())
