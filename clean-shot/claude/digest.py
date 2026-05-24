#!/usr/bin/env python3
# claude/digest.py — Clean Shot: weekly summary generator
# Produces a CB-voice-style recap of the week's road conditions,
# hazards avoided, time/money saved, and referral progress.
# Delivered: Sunday morning push notification or on-demand.
# TODO: implement in module sprint

from claude.prompts import weekly_digest_prompt


def generate_weekly_digest(config: dict, week_data: dict,
                            api_key: str = None) -> str:
    """
    Generate a weekly digest string.
    Uses Claude if api_key provided, otherwise returns a template summary.
    Stub.
    """
    if api_key:
        return _generate_with_claude(config, week_data, api_key)
    return _generate_offline(config, week_data)


def _generate_with_claude(config: dict, week_data: dict, api_key: str) -> str:
    """Call Claude API to write the digest. Stub."""
    # TODO: build prompt, call anthropic SDK
    return _generate_offline(config, week_data)


def _generate_offline(config: dict, week_data: dict) -> str:
    """Template-based offline digest. Stub."""
    city         = config.get("city", "your area")
    hazard_count = week_data.get("hazard_count", 0)
    time_saved   = week_data.get("time_saved_min", 0)
    fuel_saved   = week_data.get("fuel_saved_usd", 0.0)

    lines = [
        f"Weekly road report for {city}:",
        f"You dodged {hazard_count} hazards this week.",
    ]
    if time_saved > 0:
        lines.append(f"Saved ~{time_saved} minutes of delay.")
    if fuel_saved > 0:
        lines.append(f"Saved ~${fuel_saved:.2f} in fuel by rerouting.")
    lines.append("Keep the shiny side up and the rubber side down. 10-4.")

    return " ".join(lines)
