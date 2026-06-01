#!/usr/bin/env python3
"""
license.py — CleanShot license validation
Checks license against cleanshothq.com API on every launch.
Stores license key locally in config dir.
"""

import hashlib
import json
import os
import platform
import sys
import uuid
from pathlib import Path

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

API_BASE      = "https://api.cleanshothq.com/v1"
LICENSE_FILE  = Path.home() / ".config" / "cleanshot" / "license.json"


# ── Machine fingerprint ───────────────────────────────────────────────────────

def get_machine_id() -> str:
    """
    Generate a stable hardware fingerprint for this machine.
    Combines MAC address, hostname, CPU arch, and processor string.
    Returns first 32 hex chars of SHA-256 hash.
    """
    components = [
        str(uuid.getnode()),       # MAC address as integer
        platform.node(),           # hostname
        platform.machine(),        # e.g. AMD64, x86_64
        platform.processor(),      # CPU description string
    ]
    raw = "|".join(components)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ── Local license storage ─────────────────────────────────────────────────────

def load_local_license() -> dict | None:
    """Load saved license key from disk."""
    try:
        if LICENSE_FILE.exists():
            return json.loads(LICENSE_FILE.read_text())
    except Exception:
        pass
    return None


def save_local_license(data: dict):
    """Persist license data to disk."""
    try:
        LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        LICENSE_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


# ── API calls ─────────────────────────────────────────────────────────────────

def register(email: str, name: str = "", referral_code: str = "") -> dict:
    """
    Register a new user and start their 30-day trial.
    referral_code credits the referrer in Stripe when provided.
    Returns API response dict.
    """
    if not _HAS_REQUESTS:
        return {"allowed": True, "error": "requests_not_installed"}

    machine_id = get_machine_id()
    payload: dict = {"email": email, "name": name, "machine_id": machine_id}
    if referral_code:
        payload["ref"] = referral_code

    try:
        r = requests.post(
            f"{API_BASE}/register",
            json=payload,
            timeout=10,
        )
        data = r.json()
        if data.get("license_key"):
            save_local_license({
                "license_key": data["license_key"],
                "email": email,
                "machine_id": machine_id,
            })
        return data
    except Exception as e:
        return {"allowed": True, "error": f"network_unavailable: {e}"}


def check_license(license_key: str | None = None) -> dict:
    """
    Validate license against the API.
    Falls back to local data if network is unavailable.
    Returns dict with at minimum: {"allowed": bool, "status": str}
    """
    # Load from disk if not passed in
    local = load_local_license()
    if license_key is None:
        license_key = local.get("license_key") if local else None

    if not license_key:
        return {"allowed": False, "status": "unregistered"}

    if not _HAS_REQUESTS:
        return {"allowed": True, "status": "unknown", "error": "requests_not_installed"}

    machine_id = get_machine_id()
    try:
        r = requests.get(
            f"{API_BASE}/license",
            params={"key": license_key, "machine": machine_id},
            timeout=8,
        )
        data = r.json()
        return data
    except Exception:
        # Network unavailable — fail open so truckers aren't blocked on the road
        return {"allowed": True, "status": "unknown", "error": "network_unavailable"}


# ── Startup gate ──────────────────────────────────────────────────────────────

def enforce_license(version: str = "", config: dict | None = None):
    """
    Call at app startup. Prints status and exits if not allowed.
    Silently passes if network is unavailable (fail open).
    Pass config to enable referral code capture on registration.
    """
    local = load_local_license()

    # No license at all — prompt registration
    if not local or not local.get("license_key"):
        print("\n  Welcome to CleanShot!")
        print("  Please register for your free 30-day trial.")
        print()
        email = input("  Enter your email: ").strip()
        if not email:
            print("  Registration skipped. Some features may be limited.")
            return

        name = input("  Your name (optional): ").strip()

        # Pick up referral code from --ref= flag or install.ref file
        ref_code = ""
        if config is not None:
            try:
                from core.referral import capture_referral_code
                ref_code = capture_referral_code(config) or ""
            except Exception:
                pass

        result = register(email, name, referral_code=ref_code)

        status = result.get("status", "")
        if status == "registered":
            print(f"\n  ✅ Trial started! License key: {result['license_key']}")
            print(f"     You have 30 days. cleanshothq.com\n")
        elif status == "blocked":
            print(f"\n  ✗ {result.get('message', 'This device is not eligible.')}")
            sys.exit(1)
        elif status in ("trial_expired", "existing_trial"):
            print(f"\n  ℹ {result.get('message', '')}")
            if status == "trial_expired":
                print()
                print("  Subscribe to keep access: cleanshothq.com/subscribe")
                try:
                    import webbrowser
                    webbrowser.open("https://cleanshothq.com/subscribe")
                    print("  (Browser opened to subscription page)")
                except Exception:
                    pass
                print()
                input("  Press Enter to exit...")
                sys.exit(1)
        elif "error" in result:
            # Network error — let them through
            pass
        return

    # Have a license key — validate it
    result = check_license(local.get("license_key"))

    allowed  = result.get("allowed", True)
    status   = result.get("status", "unknown")
    msg      = result.get("message")
    days     = result.get("days_remaining")

    if not allowed:
        print(f"\n  ✗ CleanShot: {result.get('message', 'License invalid.')}")
        print()
        print("  To subscribe and keep access:")
        print("    cleanshothq.com/subscribe")
        print()
        print("  Or open in browser now:")
        try:
            import webbrowser
            webbrowser.open("https://cleanshothq.com/subscribe")
            print("    (Browser opened to subscription page)")
        except Exception:
            pass
        print()
        input("  Press Enter to exit...")
        sys.exit(1)

    # Show warnings for expiring trials
    if msg:
        print(f"\n  {msg}\n")
