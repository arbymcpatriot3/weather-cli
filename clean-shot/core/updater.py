#!/usr/bin/env python3
# core/updater.py — Clean Shot: Driver Intelligence System
# Silent background auto-update checker.
#
# Behavior:
#   - Checks once per 24 hours (last_update_check stored in config)
#   - Runs in a daemon thread — never slows startup by even 1ms
#   - Fetches VERSION file from GitHub (< 10 bytes)
#   - If newer version: runs git pull in the repo root
#   - Stores a one-line result message in config (pending_update_msg)
#   - Message shown once on the NEXT startup, then cleared
#
# Zero new dependencies.  Uses requests (already required) + subprocess git.
# Silently no-ops on any failure — update check never crashes the app.

import subprocess
import threading
import time
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────

VERSION_URL        = (
    "https://raw.githubusercontent.com/arbymcpatriot3/weather-cli"
    "/main/clean-shot/VERSION"
)
UPDATE_INTERVAL_SEC = 86_400   # 24 hours

# clean-shot/core/updater.py → parent.parent = clean-shot/ → parent = repo root
_CLEAN_SHOT_DIR = Path(__file__).resolve().parent.parent   # clean-shot/
_REPO_ROOT      = _CLEAN_SHOT_DIR.parent                   # weather-cli/ (git root)
_VERSION_FILE   = _CLEAN_SHOT_DIR / "VERSION"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _local_version() -> str:
    """Read local VERSION file. Returns '0.0.0' on any failure."""
    try:
        return _VERSION_FILE.read_text().strip()
    except Exception:
        return "0.0.0"


def _version_tuple(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0, 0, 0)


def _fetch_remote_version() -> str | None:
    """Fetch the VERSION file from GitHub. Returns None on any failure."""
    try:
        import requests
        r = requests.get(VERSION_URL, timeout=5)
        if r.status_code == 200:
            return r.text.strip()
    except Exception:
        pass
    return None


def _git_pull() -> tuple[bool, str]:
    """
    Run git pull in the repo root.
    Returns (success, output_or_error).
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "pull", "--quiet"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0, result.stdout.strip()
    except FileNotFoundError:
        return False, "git not found"
    except Exception as e:
        return False, str(e)


# ── Background worker ─────────────────────────────────────────────────────────

def _update_worker(config: dict, save_fn) -> None:
    """
    Background daemon thread: fetch remote version, pull if newer.
    Writes result to config['pending_update_msg'] for display on next startup.
    """
    remote = _fetch_remote_version()
    if not remote:
        return   # network unavailable — silent no-op

    local = _local_version()

    if _version_tuple(remote) <= _version_tuple(local):
        return   # already up to date — nothing to do

    # Newer version available — attempt silent git pull
    success, _ = _git_pull()

    if success:
        config["pending_update_msg"] = (
            f"  ✅ Clean Shot updated: v{local} → v{remote}"
            f"  (restart to apply)"
        )
    else:
        config["pending_update_msg"] = (
            f"  ℹ️  Update available: v{remote}  (you have v{local})"
            f"  Run: git pull"
        )

    try:
        save_fn(config)
    except Exception:
        pass   # never crash on save failure


# ── Public API ────────────────────────────────────────────────────────────────

def check_and_update(config: dict, save_fn) -> None:
    """
    Launch a background update check if 24+ hours have passed since last check.
    Returns immediately — NEVER blocks startup.

    Call once at startup after config is loaded:
        from core.updater import check_and_update
        check_and_update(config, save_config)
    """
    now  = time.time()
    last = float(config.get("last_update_check", 0))

    if (now - last) < UPDATE_INTERVAL_SEC:
        return   # checked recently — skip

    # Stamp the check time immediately so parallel launches don't double-check
    config["last_update_check"] = now
    try:
        save_fn(config)
    except Exception:
        pass

    t = threading.Thread(
        target=_update_worker,
        args=(config, save_fn),
        daemon=True,   # exits with the app — never hangs shutdown
    )
    t.start()


def get_pending_message(config: dict, save_fn) -> str | None:
    """
    Return the update result message from the last background check (if any).
    Clears the message after returning — shown exactly once.

    Call at startup before displaying output:
        from core.updater import get_pending_message
        msg = get_pending_message(config, save_config)
        if msg:
            print(msg)
    """
    msg = config.pop("pending_update_msg", None)
    if msg:
        try:
            save_fn(config)
        except Exception:
            pass
        return msg
    return None
