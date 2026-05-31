#!/usr/bin/env python3
# core/glossary.py — Clean Shot: icon and symbol reference for drivers.

from __future__ import annotations
import shutil

GLOSSARY: dict[str, list[tuple[str, str, str]]] = {
    "Hazard Icons": [
        ("🧊", "Black Ice Risk",
         "Road surface temp below freezing with moisture. Slow down, increase following distance."),
        ("🌉", "Bridge Freeze",
         "Bridge decks drop temp faster than roads — ice forms here first. Treat every bridge as icy."),
        ("🌫️", "Fog Advisory",
         "Visibility below 1/4 mile. Use low beams, reduce speed, increase following distance."),
        ("🌊", "Flood Risk",
         "Heavy rain or snowmelt causing road flooding. Never drive through standing water."),
        ("🫙", "Diesel Gel Risk",
         "Temp low enough to gel #2 diesel. Use anti-gel additive or switch to #1 diesel blend."),
        ("💨", "High Wind Advisory",
         "Wind speeds dangerous for high-profile vehicles. Reduce speed, grip wheel firmly."),
        ("⛰️", "Mudslide Risk",
         "Recent heavy rain on slopes. Watch for debris on roadway, especially in cut sections."),
        ("🚧", "DOT / 511 Incident",
         "Active incident from state DOT. Construction, accident, or road closure ahead."),
    ],
    "Severity Levels": [
        ("🔴", "Critical",
         "Immediate danger. Stop if safe to do so, take alternate route."),
        ("🟠", "High",
         "Significant hazard. Reduce speed and use caution for the next several miles."),
        ("🟡", "Moderate",
         "Be aware. Monitor conditions — hazard is present but manageable."),
        ("🟢", "Low / Clear",
         "No significant hazard detected at this time."),
    ],
    "Status Symbols": [
        ("✅", "OK / Active",      "Feature is working normally and returning live data."),
        ("⚠️", "Warning",          "Condition requires your attention."),
        ("❌", "Error / Unavailable", "Feature unavailable or data could not be retrieved."),
        ("📡", "Live Data",        "Pulling from a live DOT/511 or weather feed right now."),
        ("🅿️", "Parking",          "Truck stop or rest area within your HOS runway."),
        ("⏱️", "HOS Status",       "Hours of Service advisory — check your remaining drive time."),
        ("📢", "Voice Alert",      "Text-to-speech alert played or queued."),
        ("🔄", "Auto-refresh",     "Continuous monitoring mode is active."),
        ("📶", "Signal",           "Data connection status indicator."),
    ],
    "Truck Stop Amenities": [
        ("🍔", "Food",     "Restaurant or food service on site."),
        ("🚿", "Showers",  "Shower facilities available — call ahead to confirm wait times."),
        ("🔌", "Electric", "Shore power / electric hookup available."),
        ("🔧", "Repair",   "Truck repair or service bay on site."),
        ("⛽", "Fuel",     "Diesel fuel available."),
        ("📶", "WiFi",     "WiFi available."),
        ("⚖️", "Scales",   "CAT certified automated truck scales on site."),
    ],
    "HOS Indicators": [
        ("🟢", "HOS OK",       "Drive time available — you are within safe limits."),
        ("🟡", "HOS Warning",  "Less than 2 hours of drive time remaining."),
        ("🔴", "HOS Critical", "Less than 30 minutes of drive time remaining."),
        ("⛔", "HOS Limit",    "No drive time remaining. 10-hour rest is required by law."),
    ],
}


def show_glossary(config: dict | None = None) -> None:
    """Display the full icon glossary with pagination by section."""
    try:
        import colorama
        colorama.init()
        YELLOW = "\033[93m"
        CYAN   = "\033[96m"
        RESET  = "\033[0m"
        BOLD   = "\033[1m"
        DIM    = "\033[2m"
    except ImportError:
        YELLOW = CYAN = RESET = BOLD = DIM = ""

    w     = shutil.get_terminal_size(fallback=(80, 40)).columns
    w     = max(60, min(w, 120))
    div   = "─" * min(w - 2, 58)
    sections = list(GLOSSARY.items())

    print()
    print(f"  {BOLD}{YELLOW}{'═' * min(w - 2, 58)}{RESET}")
    print(f"  {BOLD}  CleanShot — Icon & Symbol Glossary{RESET}")
    print(f"  {YELLOW}{'═' * min(w - 2, 58)}{RESET}")

    for i, (section_name, entries) in enumerate(sections):
        print()
        print(f"  {CYAN}{BOLD}{section_name}{RESET}")
        print(f"  {div}")

        for icon, name, desc in entries:
            # Wrap description if terminal is narrow
            max_desc = w - 16
            if len(desc) > max_desc:
                desc = desc[:max_desc - 3] + "..."
            print(f"  {icon}  {BOLD}{name:<22}{RESET}  {DIM}{desc}{RESET}")

        # Paginate every 2 sections (not after the last one)
        if i < len(sections) - 1 and (i + 1) % 2 == 0:
            print()
            print(f"  {DIM}── Press Enter for more, Q to return to menu ──{RESET}", end="", flush=True)
            try:
                key = input()
                if key.strip().lower() == "q":
                    print()
                    return
            except (KeyboardInterrupt, EOFError):
                print()
                return

    print()
    print(f"  {div}")
    print(f"  {DIM}Press Enter to return to menu.{RESET}", end="", flush=True)
    try:
        input()
    except (KeyboardInterrupt, EOFError):
        pass
    print()
