#!/usr/bin/env python3
# claude/prompts.py — Clean Shot: all Claude prompt templates
# Centralizes every prompt string so they can be tuned together.
# Hazard parsing, pattern detection, weekly digest, and CB voice alerts.

# ── CB Radio Style Voice Alerts ───────────────────────────────────────────────
# Tone: friendly, concise, CB radio culture, never alarming.
# Always ends with a safety action ("back it down", "watch your step").

_CB_VOICE_ALERTS = {
    "black_ice":       "Smokey's reporting black ice ahead good buddy — back it down",
    "fog":             "We got a ground-hugger ahead — slow your roll and keep it on the white line",
    "flood":           "Water on the road ahead breaker — don't drown that rig",
    "high_wind":       "Got some hammer lane wind at your door — watch that trailer",
    "diesel_gel":      "Breaker breaker — temps are dropping, your diesel might be gelling up",
    "heavy_snow":      "Snow's coming down hard out there — might be time to find a chicken coop",
    "ice_storm":       "It's a skating rink out there good buddy — park it if you can",
    "thunderstorm":    "Got some steel rain moving in — eye out for lightning and hydroplaning",
    "tornado_watch":   "Twister weather on deck — keep your ears on and find low ground",
    "hurricane":       "Big blow coming through — get off the road and tie her down",
    "heat_advisory":   "Scorcher out there — check your tires and drink some water",
    "bridge_freeze":   "Watch those bridge decks driver — they freeze before the road does",
    "mudslide":        "Got some heavy rain that might be moving dirt around good buddy — watch for debris on the road",
    "hazard_reported": "Got a community report ahead — eyes up and slow your roll",
    "hos_warning":     "You're burning daylight on your clock good buddy — start looking for a spot",
    "parking_ahead":   "Got a truck stop in your runway — might be worth a look",
    "bridge_clearance": "Watch your roof good buddy — low clearance bridge ahead, check your height",
    "weigh_open":       "Chicken coop's open ahead driver — get your paperwork ready",
    "road_closure":     "Road's shut down up there — find another way around",
    "chain_control":    "Chain law in effect ahead good buddy — wrap up those tires",
    "weight_restrict":  "Weight restriction on that road driver — check your gross before you roll",
    "incident":         "Got a road incident ahead good buddy — eyes up and slow your roll",
    "weather_advisory": "Weather advisory on your route driver — check conditions before you push",
}

# ── Hazard Parsing Prompt ────────────────────────────────────────────────────

HAZARD_PARSE_PROMPT = """You are parsing a trucker's road hazard report.
Extract structured data from this free-text report.

Report: "{text}"

Return ONLY valid JSON with these fields:
{{
  "type": one of [black_ice, fog, flood, accident, debris, construction,
                  weigh_station, parking_full, diesel_shortage, other],
  "severity": one of [low, medium, high],
  "direction": one of [northbound, southbound, eastbound, westbound, both, unknown],
  "cleared": boolean (true if driver says it's cleared),
  "notes": "brief cleaned-up description under 50 chars"
}}

If the report is too vague, return {{"type": "other", "severity": "low",
"direction": "unknown", "cleared": false, "notes": "{text[:40]}"}}
"""

# ── Pattern Detection Prompt ─────────────────────────────────────────────────

PATTERN_DETECT_PROMPT = """You are analyzing a cluster of road hazard reports
from different drivers along the same corridor.

Reports (JSON array): {reports_json}

Determine:
1. Is there a meaningful pattern (same hazard type, same area)?
2. What is the combined severity?
3. What is the best single-sentence CB radio style alert for this cluster?

Return ONLY valid JSON:
{{
  "is_pattern": boolean,
  "hazard_type": string,
  "severity": "low"|"medium"|"high"|"critical",
  "driver_count": integer,
  "cb_alert": "CB radio style alert string under 80 chars"
}}
"""

# ── Weekly Digest Prompt ─────────────────────────────────────────────────────

WEEKLY_DIGEST_PROMPT = """You are writing a weekly road conditions summary
for a trucker who runs the {route_desc} corridor.

Data from the past 7 days:
- Weather events: {weather_summary}
- Hazard reports: {hazard_count} reports, top types: {top_hazards}
- Time/money saved by avoiding hazards: {savings_summary}
- Referral count this week: {new_referrals}

Write a friendly 3-4 sentence weekly digest in the voice of a CB radio
dispatcher. Mention the weather, any notable hazards, and the driver's
savings. Keep it under 200 words. No emojis. Trucker-friendly tone.
"""


# ── Public API ────────────────────────────────────────────────────────────────

def cb_voice_alert(alert_type: str) -> str:
    """Return the CB radio voice string for a known alert type."""
    return _CB_VOICE_ALERTS.get(alert_type, "")


def hazard_parse_prompt(text: str) -> str:
    """Format the hazard parsing prompt with driver's report text."""
    return HAZARD_PARSE_PROMPT.format(text=text)


def pattern_detect_prompt(reports: list) -> str:
    """Format the pattern detection prompt with a list of report dicts."""
    import json
    return PATTERN_DETECT_PROMPT.format(reports_json=json.dumps(reports))


def weekly_digest_prompt(route_desc: str, weather_summary: str,
                         hazard_count: int, top_hazards: str,
                         savings_summary: str, new_referrals: int) -> str:
    return WEEKLY_DIGEST_PROMPT.format(
        route_desc=route_desc,
        weather_summary=weather_summary,
        hazard_count=hazard_count,
        top_hazards=top_hazards,
        savings_summary=savings_summary,
        new_referrals=new_referrals,
    )
