#!/usr/bin/env python3
# display/replaces.py — Clean Shot: what does this replace?
# "cleanshot replaces" — full or short comparison display.
# Shows apps replaced, savings math, data comparison, time savings.
# Blue Collar Nation LLC

import shutil

# ── App catalog ───────────────────────────────────────────────────────────────
# (category, app_name, monthly_price_usd)
_APPS = [
    ("WEATHER",            "Weather Channel",    9.99),
    ("WEATHER",            "Drive Weather",      4.99),
    ("WEATHER",            "MyRadar",            2.99),
    ("WEATHER",            "AccuWeather",        3.99),
    ("NAVIGATION & ROADS", "Trucker Path Pro",   9.99),
    ("NAVIGATION & ROADS", "Sygic Truck GPS",   14.99),
    ("NAVIGATION & ROADS", "CoPilot Truck",     14.99),
    ("NAVIGATION & ROADS", "TruckMap Pro",       4.99),
    ("FUEL",               "GasBuddy Premium",   9.99),
    ("FUEL",               "Fuelbook",           4.99),
    ("PARKING",            "Truck Parking Club", 9.99),
    ("HOS & COMPLIANCE",   "BigRoad ELD",       20.00),
    ("HOS & COMPLIANCE",   "Drivewyze",         16.99),
    ("DOCUMENTS",          "CamScanner Pro",     4.99),
    ("HEALTH & WELLNESS",  "Rolling Strong",     4.99),
    ("FAMILY",             "Life360 Pro",        7.99),
    ("MAINTENANCE",        "TruckFaults",        3.99),
    ("MAINTENANCE",        "Fleetio Go",         5.00),
    ("FINANCIAL",          "IFTA tracking",      9.99),
    ("FINANCIAL",          "Mileage log apps",   4.99),
]

CLEAN_SHOT_PRICE_MO = 29.99   # Solo Pro monthly price


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sep(w: int = 39) -> str:
    try:
        cols = max(36, shutil.get_terminal_size().columns - 2)
    except Exception:
        cols = 78
    return "━" * min(w, cols)


def total_app_cost_mo() -> float:
    return sum(p for _, _, p in _APPS)


def monthly_savings() -> float:
    return total_app_cost_mo() - CLEAN_SHOT_PRICE_MO


def annual_savings() -> float:
    return monthly_savings() * 12


def get_tts_summary() -> str:
    """Short TTS pitch — under 200 chars."""
    n    = len(_APPS)
    save = int(annual_savings() / 100) * 100   # round down to nearest $100
    return (
        f"Clean Shot replaces {n} apps "
        f"and saves you over {save:,} dollars a year. "
        f"Works everywhere including dead zones on 2G. "
        f"One app. One subscription. "
        f"Free for 30 days. "
        f"cleanshothq.com"
    )


# ── Public display ────────────────────────────────────────────────────────────

def display_replaces(config: dict = None, short: bool = False) -> None:
    """Print full or short version of what Clean Shot replaces."""
    if short:
        _short()
    else:
        try:
            from core.config import VERSION
        except Exception:
            VERSION = "3.0"
        _full(VERSION)


# ── Short version (6 lines — shown on first run) ──────────────────────────────

def _short() -> None:
    sep = _sep()
    n       = len(_APPS)
    save_yr = annual_savings()
    print()
    print(f"  {sep}")
    print(f"  💰 CLEAN SHOT SAVES YOU")
    print()
    print(f"  {n} apps → 1 app")
    print(f"  ${save_yr:,.0f}/yr saved")
    print(f"  1.5GB/mo data saved")
    print(f"  4hrs/week time saved")
    print(f"  Works on 2G everywhere")
    print()
    print(f"  Try free: cleanshothq.com")
    print(f"  {sep}")
    print()


# ── Full version ──────────────────────────────────────────────────────────────

def _full(version: str) -> None:
    sep      = _sep()
    n        = len(_APPS)
    total_mo = total_app_cost_mo()
    total_yr = total_mo * 12
    cs_yr    = CLEAN_SHOT_PRICE_MO * 12
    save_mo  = monthly_savings()
    save_yr  = annual_savings()
    save_5yr = save_yr * 5

    print()
    print(f"  {sep}")
    print(f"  🚛 CLEAN SHOT v{version}")
    print(f"     Driver Intelligence System")
    print(f"     By Blue Collar Nation LLC")
    print(f"  {sep}")
    print()
    print(f"  📱 APPS THIS REPLACES:")
    print()

    cat = None
    for c, name, price in _APPS:
        if c != cat:
            cat = c
            print(f"  {c}:")
        print(f"  ✅ {name:<22}  ${price:>5.2f}/mo")

    print()
    print(f"  {sep}")
    print()
    print(f"  💰 THE MATH:")
    print()
    print(f"  Apps replaced:        {n:>4}")
    print(f"  Their monthly cost:  ${total_mo:>7.2f}")
    print(f"  Their annual cost:   ${total_yr:>7.2f}")
    print()
    print(f"  CLEAN SHOT PRO:      ${CLEAN_SHOT_PRICE_MO:>7.2f}/mo")
    print(f"  Annual cost:         ${cs_yr:>7.2f}")
    print()
    print(f"  YOUR SAVINGS:")
    print(f"    Monthly:    ${save_mo:>8.2f}")
    print(f"    Annual:     ${save_yr:>8.2f}")
    print(f"    5 Years:    ${save_5yr:>8.2f}")
    print()
    print(f"  {sep}")
    print()
    print(f"  📡 DATA USAGE COMPARISON:")
    print()
    print(f"  Other apps combined:")
    print(f"    ~50MB per day")
    print(f"    ~1.5GB per month")
    print()
    print(f"  Clean Shot:")
    print(f"    ~50KB per refresh")
    print(f"    ~5MB per month")
    print()
    print(f"  DATA SAVED:")
    print(f"    Daily:    ~49.95MB")
    print(f"    Monthly:  ~1.495GB")
    print(f"    Annual:   ~17.94GB")
    print()
    print(f"  That's real money on")
    print(f"  limited data plans.")
    print(f"  Works on 2G. Always.")
    print()
    print(f"  {sep}")
    print()
    print(f"  ⏱️  TIME SAVED PER WEEK:")
    print()
    print(f"  Managing {n} apps:      ~2hrs")
    print(f"  Switching between:    ~1hr")
    print(f"  Finding parking:     ~45min")
    print(f"  Checking weather:    ~30min")
    print()
    print(f"  With Clean Shot:")
    print(f"  Everything in one place.")
    print(f"  One command. 30 seconds.")
    print()
    print(f"  TIME SAVED: ~4hrs/week")
    print(f"  ANNUAL:     ~208hrs/year")
    print(f"  AT $30/hr:  $6,240/year")
    print()
    print(f"  {sep}")
    print()
    print(f"  🌄 WORKS EVERYWHERE:")
    print()
    print(f"  ✅ Rural highways")
    print(f"  ✅ Remote mountain passes")
    print(f"  ✅ Dead zones")
    print(f"  ✅ 2G connections")
    print(f"  ✅ Offline mode available")
    print(f"  ✅ Cached data when no signal")
    print(f"  ✅ Never requires WiFi")
    print(f"  ✅ Works on any phone")
    print(f"  ✅ Works on old hardware")
    print()
    print(f"  {sep}")
    print()
    print(f"  🏆 ONE APP. ONE LOGIN.")
    print(f"     ONE SUBSCRIPTION.")
    print()
    print(f"     FREE for 30 days.")
    print(f"     No credit card needed.")
    print(f"     Cancel anytime.")
    print()
    print(f"     cleanshothq.com")
    print(f"  {sep}")
    print()
