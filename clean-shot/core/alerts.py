#!/usr/bin/env python3
# core/alerts.py — Clean Shot: weather-derived road hazard alert engine
# 100% offline — all logic runs on cached Open-Meteo data
# Zero additional API calls.  Data budget: uses existing weather cache (~12 KB).
#
# Alert types:
#   black_ice      — 28-34°F + precipitation probability
#   bridge_freeze  — bridge decks freeze ~4-5°F before road surface
#   fog            — weather code 45/48 (fog / icy fog)
#   flood          — heavy rain codes + sustained high precip probability
#   diesel_gel     — below 20°F (B20 gels at 10-15°F, B5 at -5°F)
#   high_wind      — crosswind danger, adjusted per vehicle type
#   mudslide       — sustained heavy rainfall risk indicator
#
# Severity: CRITICAL | WARNING | INFO
# Sort order: CRITICAL first, then WARNING, then INFO

# ── Thresholds ────────────────────────────────────────────────────────────────

# Black ice
_ICE_TEMP_HIGH     = 34.0   # °F upper bound — warmer than this, won't form
_ICE_TEMP_LOW      = 20.0   # °F lower bound — colder, it's just hard ice
_ICE_PRECIP_PCT    = 20     # % precip probability minimum to trigger

# Bridge freeze (bridges lose heat from both top and bottom — freeze sooner)
_BRIDGE_WARN_TEMP  = 38.0   # °F — bridges can freeze above freezing air temp
_BRIDGE_CRIT_TEMP  = 32.0   # °F — guaranteed ice on bridge decks

# Fog — Open-Meteo weather codes
_FOG_CODES         = {45, 48}   # 45=fog, 48=icy fog (depositing rime)

# Heavy rain / flood codes
_HEAVY_RAIN_CODES  = {65, 67, 82}   # heavy rain, heavy freezing rain, violent showers
_FLOOD_PRECIP_PCT  = 60             # % sustained probability to trigger
_FLOOD_WINDOW_H    = 6              # hours to look ahead

# Diesel gel temperatures
_GEL_WATCH         = 20.0   # °F — approaching gel range, time to add anti-gel
_GEL_WARNING       = 15.0   # °F — B20 biodiesel blends gelling now
_GEL_CRITICAL      = 0.0    # °F — even B5 blends at risk

# Wind — vehicle type sensitivity multipliers (applied to config wind_alert_mph)
_WIND_FACTOR = {
    "semi":    1.00,   # baseline
    "box":     0.90,   # enclosed box, more sail area
    "flatbed": 1.10,   # low-profile, slightly more stable
    "tanker":  0.85,   # high center of gravity + round profile
    "rv":      0.80,   # most susceptible
}
_WIND_BASE_MPH     = 40.0   # default if not set in config

# Mudslide — no terrain data, so flag based on rainfall intensity alone
_MUDSLIDE_PCT      = 80     # % precip probability to count as "heavy"
_MUDSLIDE_HOURS    = 3      # consecutive hours at that level


# ── Alert builder ─────────────────────────────────────────────────────────────

def _alert(alert_type: str, severity: str, title: str,
           message: str, cb_voice: str, triggered_by: str) -> dict:
    """Build a standardized alert dict."""
    return {
        "type":         alert_type,
        "severity":     severity,
        "title":        title,
        "message":      message,
        "cb_voice":     cb_voice,
        "triggered_by": triggered_by,
    }


# ── Detectors ─────────────────────────────────────────────────────────────────

def _check_black_ice(current: dict, hourly: dict):
    temp  = current.get("temp", 99)
    code  = current.get("code", 0)

    # Only in the ice-forming window
    if not (_ICE_TEMP_LOW <= temp <= _ICE_TEMP_HIGH):
        return None

    # Precipitation: current code or upcoming probability
    _precip_codes = {51,53,55,56,57,61,63,65,66,67,71,73,75,77,80,81,82,85,86}
    current_precip = code in _precip_codes
    probs = hourly.get("precip_probs", [])
    next_6h_pct = max(probs[:6]) if probs else 0

    if not (current_precip or next_6h_pct >= _ICE_PRECIP_PCT):
        return None

    if temp <= 30:
        severity = "CRITICAL"
        cb = (f"Breaker breaker — black ice at {temp:.0f} degrees good buddy, "
              f"back it WAY down and watch those brakes")
    else:
        severity = "WARNING"
        cb = (f"Smokey's reporting black ice ahead good buddy — "
              f"she's {temp:.0f} degrees and slick, back it down")

    return _alert(
        "black_ice", severity,
        f"Black Ice Risk  {temp:.0f}°F",
        (f"Temp {temp:.0f}°F with {next_6h_pct:.0f}% precip probability. "
         f"Pavement and bridge decks may have black ice. "
         f"Reduce speed, increase following distance, avoid hard braking."),
        cb,
        f"temp={temp:.1f}°F  precip_code={current_precip}  next_6h_pct={next_6h_pct:.0f}%",
    )


def _check_bridge_freeze(current: dict):
    temp = current.get("temp", 99)

    if temp > _BRIDGE_WARN_TEMP:
        return None

    if temp <= _BRIDGE_CRIT_TEMP:
        severity = "CRITICAL"
        title    = f"Bridge Freeze  {temp:.0f}°F"
        msg      = (f"Temp {temp:.0f}°F — bridge decks ARE freezing. "
                    f"Bridges lose heat from above and below, freezing before road surface.")
        cb       = (f"Double-check those bridge decks good buddy — "
                    f"it's {temp:.0f} degrees and those overpasses are ice sheets right now")
    else:
        severity = "WARNING"
        title    = f"Bridge Freeze Warning  {temp:.0f}°F"
        msg      = (f"Temp {temp:.0f}°F — bridge decks may be freezing. "
                    f"Bridges freeze 4-5°F before the road surface.")
        cb       = (f"Watch those bridge decks driver — "
                    f"at {temp:.0f} degrees they freeze before the road does")

    return _alert("bridge_freeze", severity, title, msg, cb,
                  f"temp={temp:.1f}°F <= bridge_warn={_BRIDGE_WARN_TEMP}°F")


def _check_fog(current: dict, hourly: dict):
    code = current.get("code", 0)

    if code not in _FOG_CODES:
        return None

    if code == 48:
        # Icy fog — actively deposits ice on surfaces
        severity = "CRITICAL"
        title    = "Icy Fog (Freezing Fog)"
        msg      = ("Freezing fog (icy fog) reported. Near-zero visibility with "
                    "ice actively depositing on road surface, bridge decks, and vehicle.")
        cb       = ("We got a real ground-hugger out there good buddy — "
                    "icy fog, near-zero viz, ice building on the road, take it real easy")
    else:
        severity = "WARNING"
        title    = "Dense Fog"
        msg      = ("Fog reported. Visibility may be under 1/4 mile. "
                    "Use low beams, not high beams. Reduce speed, "
                    "increase following distance significantly.")
        cb       = ("Got a ground-hugger ahead — slow your roll and keep it "
                    "on the white line, visibility's real poor out there")

    return _alert("fog", severity, title, msg, cb, f"weather_code={code}")


def _check_flood(current: dict, hourly: dict, forecast: list):
    code        = current.get("code", 0)
    probs       = hourly.get("precip_probs", [0]*24)
    today_rain  = forecast[0].get("rain_prob", 0) if forecast else 0

    current_heavy  = code in _HEAVY_RAIN_CODES
    next_6h_max    = max(probs[:_FLOOD_WINDOW_H]) if probs else 0
    sustained_6h   = sum(1 for p in probs[:_FLOOD_WINDOW_H] if p >= _FLOOD_PRECIP_PCT)

    # Trigger if heavy rain is happening OR sustained high probability ahead
    if not (current_heavy or sustained_6h >= 3 or
            (next_6h_max >= _FLOOD_PRECIP_PCT and today_rain >= _FLOOD_PRECIP_PCT)):
        return None

    if current_heavy and today_rain >= 80:
        severity = "CRITICAL"
        cb       = ("Water on the road ahead breaker — "
                    "don't drown that rig, find high ground")
    elif next_6h_max >= 80:
        severity = "WARNING"
        cb       = (f"Heavy rain rolling in good buddy — "
                    f"{next_6h_max:.0f}% chance next few hours, "
                    f"watch for water across the road")
    else:
        severity = "INFO"
        cb       = (f"Got some heavy rain possible today driver — "
                    f"{today_rain:.0f}% chance, watch for low spots and underpasses")

    return _alert(
        "flood", severity,
        f"Flood / Road Washout Risk  ({today_rain:.0f}% rain today)",
        ("Heavy precipitation possible. Watch for road washouts, "
         "flooded underpasses, and water across the roadway. "
         "Never drive through standing water — 6 inches can float a vehicle."),
        cb,
        f"code={code}  next_6h={next_6h_max:.0f}%  sustained_6h={sustained_6h}h  today={today_rain:.0f}%",
    )


def _check_diesel_gel(current: dict, hourly: dict):
    temp   = current.get("temp", 99)
    temps  = hourly.get("temps", [])
    low_6h = min(temps[:6]) if temps else temp
    worst  = min(temp, low_6h)  # use coldest upcoming temp for worst-case

    if worst > _GEL_WATCH:
        return None

    if worst <= _GEL_CRITICAL:
        severity = "CRITICAL"
        title    = f"Diesel Gel  CRITICAL  {worst:.0f}°F"
        msg      = (f"Temp {worst:.0f}°F — even B5 diesel blends are at gel risk. "
                    f"Add anti-gel immediately. Keep engine running if safe. "
                    f"Check fuel filter for wax buildup.")
        cb       = (f"Breaker breaker — it's {worst:.0f} degrees, "
                    f"your diesel is gelling up right now, get that anti-gel in before she quits on you")
    elif worst <= _GEL_WARNING:
        severity = "WARNING"
        title    = f"Diesel Gel Warning  {worst:.0f}°F"
        msg      = (f"Temp {worst:.0f}°F — B20 biodiesel blends gel between 10-15°F. "
                    f"Add diesel anti-gel additive now. Switch to winter blend if available.")
        cb       = (f"Watch your fuel good buddy — "
                    f"at {worst:.0f} degrees that B20 diesel starts getting thick on you")
    else:
        severity = "INFO"
        title    = f"Diesel Gel Watch  {worst:.0f}°F"
        msg      = (f"Temp {worst:.0f}°F — approaching diesel gel range. "
                    f"Monitor fuel filter. Add anti-gel additive as precaution.")
        cb       = (f"Temperature's dropping to {worst:.0f} degrees driver — "
                    f"might want to think about that diesel anti-gel before it gets too cold")

    return _alert("diesel_gel", severity, title, msg, cb,
                  f"temp={temp:.1f}°F  min_next_6h={low_6h:.1f}°F  worst={worst:.1f}°F")


def _check_high_wind(current: dict, hourly: dict, config: dict):
    vtype     = config.get("vehicle_type", "semi")
    base      = config.get("wind_alert_mph", _WIND_BASE_MPH)
    factor    = _WIND_FACTOR.get(vtype, 1.0)
    threshold = base * factor

    wind_now  = current.get("wind_speed", 0)
    gust_now  = current.get("wind_gust", 0)
    gusts     = hourly.get("wind_gusts", [0]*24)
    max_12h   = max(gusts[:12]) if gusts else 0
    peak      = max(gust_now, max_12h)

    if peak < threshold * 0.75:
        return None

    height     = config.get("vehicle_height_ft")
    height_str = f" — {height} ft vehicle" if height else ""

    if peak >= threshold * 1.5:
        severity = "CRITICAL"
        cb       = (f"Major wind event rolling through good buddy — "
                    f"gusts to {peak:.0f} mph, consider pulling over "
                    f"until it passes, that {vtype} is gonna get pushed around")
    elif peak >= threshold:
        severity = "WARNING"
        cb       = (f"Got some hammer lane wind at your door driver — "
                    f"gusts up to {peak:.0f} mph, watch that trailer and "
                    f"keep both hands on the wheel")
    else:
        severity = "INFO"
        cb       = (f"Bit of a breeze building out there — "
                    f"{peak:.0f} mph gusts possible, keep two hands on the wheel")

    return _alert(
        "high_wind", severity,
        f"High Wind / Crosswind  {peak:.0f} mph gusts{height_str}",
        (f"Wind gusts up to {peak:.0f} mph. High crosswind danger for "
         f"{vtype}-type vehicles{height_str}. "
         f"Secure all loads. Current wind: {wind_now:.0f} mph."),
        cb,
        f"gust_now={gust_now:.1f}  max_12h={max_12h:.1f}  threshold={threshold:.1f}  vehicle={vtype}",
    )


def _check_mudslide(current: dict, hourly: dict, forecast: list):
    """
    Mudslide/debris risk indicator.
    No terrain data is available, so this flags sustained heavy rainfall
    conditions that typically precede mudslides. Relevant in hilly/mountain terrain.
    """
    probs      = hourly.get("precip_probs", [0]*24)
    today_rain = forecast[0].get("rain_prob", 0) if forecast else 0
    code       = current.get("code", 0)

    # Count consecutive hours of heavy precip probability
    heavy_hours = sum(1 for p in probs[:_MUDSLIDE_HOURS] if p >= _MUDSLIDE_PCT)
    current_violent = code in _HEAVY_RAIN_CODES

    if heavy_hours < _MUDSLIDE_HOURS and not (current_violent and today_rain >= 80):
        return None

    severity = "WARNING" if (current_violent and today_rain >= 80) else "INFO"

    return _alert(
        "mudslide", severity,
        f"Mudslide / Debris Risk  ({today_rain:.0f}% rain today)",
        ("Sustained heavy rainfall may cause mudslides and road washouts "
         "in hilly or mountainous terrain. Watch for debris on roadway, "
         "hillside runoff, road shoulder erosion, and rock falls."),
        ("Got some heavy rain that might be moving dirt around good buddy — "
         "watch for debris on the road, especially in hilly country"),
        f"heavy_hours={heavy_hours}/{_MUDSLIDE_HOURS}  today_rain={today_rain:.0f}%  code={code}",
    )


# ── Master function ───────────────────────────────────────────────────────────

_SEVERITY_ORDER = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}


def get_road_alerts(lat: float, lon: float, parsed: dict,
                    config: dict = None, tier: str = "free") -> list:
    """
    Run all offline road hazard detectors against cached weather data.

    Args:
        lat, lon  : current position (reserved for future geo-lookup)
        parsed    : output of core.weather.build_parsed()
        config    : driver config dict (vehicle_type, wind_alert_mph, etc.)
        tier      : subscription tier — all 7 detectors run for all tiers

    Returns:
        List of alert dicts sorted CRITICAL → WARNING → INFO.
        Empty list = no hazards detected.
        Each alert: { type, severity, title, message, cb_voice, triggered_by }
    """
    if config is None:
        config = {}
    if not parsed:
        return []

    current  = parsed.get("current",  {})
    hourly   = parsed.get("hourly",   {})
    forecast = parsed.get("forecast", [{}])

    candidates = [
        _check_black_ice(current, hourly),
        _check_bridge_freeze(current),
        _check_fog(current, hourly),
        _check_flood(current, hourly, forecast),
        _check_diesel_gel(current, hourly),
        _check_high_wind(current, hourly, config),
        _check_mudslide(current, hourly, forecast),
    ]

    alerts = [a for a in candidates if a is not None]
    alerts.sort(key=lambda a: _SEVERITY_ORDER.get(a["severity"], 99))
    return alerts


# ── Convenience helpers ───────────────────────────────────────────────────────

def diesel_gel_risk(temp_f: float) -> str:
    """Return 'none' | 'watch' | 'warning' | 'emergency' based on temp."""
    if temp_f > _GEL_WATCH:
        return "none"
    if temp_f > _GEL_WARNING:
        return "watch"
    if temp_f > _GEL_CRITICAL:
        return "warning"
    return "emergency"


def has_critical(alerts: list) -> bool:
    """True if any CRITICAL alert is in the list."""
    return any(a["severity"] == "CRITICAL" for a in alerts)


def filter_by_severity(alerts: list, severity: str) -> list:
    """Return only alerts matching the given severity level."""
    return [a for a in alerts if a["severity"] == severity]
