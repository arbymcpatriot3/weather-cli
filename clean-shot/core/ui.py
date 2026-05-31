#!/usr/bin/env python3
# core/ui.py — Clean Shot: platform-aware display utilities.
# Import this instead of calling os/sys platform checks inline.

from __future__ import annotations
import os
import sys
import shutil


def is_mobile() -> bool:
    """True when running on Android (Termux) or iOS (iSH)."""
    if os.environ.get("TERMUX_VERSION"):
        return True
    if "com.termux" in os.environ.get("PREFIX", ""):
        return True
    # iSH on iOS reports Linux with a very small terminal
    if sys.platform == "linux" and os.path.exists("/etc/alpine-release"):
        return True
    return False


def is_windows() -> bool:
    return sys.platform == "win32"


def is_termux() -> bool:
    return bool(os.environ.get("TERMUX_VERSION") or
                "com.termux" in os.environ.get("PREFIX", ""))


def clear_screen() -> None:
    """Cross-platform terminal clear."""
    try:
        if is_windows():
            os.system("cls")
        else:
            os.system("clear")
    except Exception:
        # Last resort: print newlines
        print("\n" * 40)


def get_terminal_size(default_cols: int = 80, default_lines: int = 40) -> tuple[int, int]:
    """Return (columns, lines), falling back to safe defaults."""
    try:
        sz = shutil.get_terminal_size(fallback=(default_cols, default_lines))
        return sz.columns, sz.lines
    except Exception:
        return default_cols, default_lines


def supports_color() -> bool:
    """True when the terminal likely renders ANSI color codes."""
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    if os.environ.get("NO_COLOR"):
        return False
    if is_windows():
        # Windows Terminal and modern ConHost support ANSI
        return (os.environ.get("WT_SESSION") is not None or
                os.environ.get("TERM_PROGRAM") == "vscode" or
                _windows_ansi_supported())
    return True


def _windows_ansi_supported() -> bool:
    """Check if Windows console has ANSI processing enabled."""
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode   = ctypes.c_ulong()
        kernel.GetConsoleMode(handle, ctypes.byref(mode))
        return bool(mode.value & 0x0004)   # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        return False


def supports_tts() -> bool:
    """True when at least one TTS engine is likely available."""
    if is_windows():
        try:
            import pyttsx3  # noqa: F401
            return True
        except ImportError:
            pass
        try:
            import win32com.client  # noqa: F401
            return True
        except ImportError:
            pass
        return False

    if is_termux():
        import shutil as _sh
        return _sh.which("termux-tts-speak") is not None

    # Linux/macOS: try common engines
    import shutil as _sh
    return any(_sh.which(e) for e in ("piper", "festival", "espeak-ng", "espeak", "say"))


def supports_sound() -> bool:
    """True when audio output is likely available."""
    if is_mobile():
        import shutil as _sh
        return _sh.which("termux-media-player") is not None or _sh.which("play") is not None
    if is_windows():
        return True  # Windows always has winsound
    import shutil as _sh
    return any(_sh.which(p) for p in ("play", "aplay", "paplay", "afplay"))


def readable_platform() -> str:
    """Human-readable platform name for display in doctor/help."""
    if is_termux():
        return "Android (Termux)"
    if sys.platform == "win32":
        return "Windows"
    if sys.platform == "darwin":
        return "macOS"
    if os.path.exists("/etc/alpine-release"):
        return "iOS (iSH / Alpine)"
    return "Linux"
