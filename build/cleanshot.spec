# cleanshot.spec -- PyInstaller spec for Clean Shot Windows executable
# Run from D:\weather-cli: pyinstaller build\cleanshot.spec
# Output: dist\cleanshot.exe

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# --- Paths -------------------------------------------------------------------
SPEC_DIR  = Path(SPECPATH)                          # D:\weather-cli\build
APP_ROOT  = str(SPEC_DIR.parent / 'clean-shot')    # D:\weather-cli\clean-shot
ENTRY     = str(SPEC_DIR.parent / 'clean-shot' / 'platforms' / 'windows' / 'main.py')
ICON_FILE = str(SPEC_DIR.parent / 'assets' / 'cleanshot.ico')

# Make app packages importable for collect_submodules
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

# --- Module collection -------------------------------------------------------
hidden = (
    collect_submodules('core')              +
    collect_submodules('platforms.windows') +
    collect_submodules('claude')            +
    collect_submodules('requests')          +
    collect_submodules('colorama')          +
    collect_submodules('pyttsx3')           +
    ['win32com', 'win32com.client', 'win32api', 'win32con', 'winreg']
    # NOTE: 'display' is intentionally absent from hiddenimports.
    # PyInstaller 6.20 collects display/__init__ but silently drops all
    # submodules.  We ship display/ as raw source via datas instead.
)

# --- Data files --------------------------------------------------------------
datas = (
    # display/ shipped as source files into _MEIPASS\display\
    # _MEIPASS is sys.path[0] at runtime, so `import display.full` resolves
    # to _MEIPASS\display\full.py without any PYZ involvement.
    [(str(Path(APP_ROOT) / 'display'), 'display')]
    + collect_data_files('core.i18n', includes=['*.json'])
)

# ─────────────────────────────────────────────────────────────────────────────
block_cipher = None

a = Analysis(
    [ENTRY],
    pathex=[APP_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude display from PYZ -- avoids the PYZ init shadowing the
        # filesystem package we ship via datas.
        'display',
        # Non-Windows platforms
        'platforms.linux',
        'platforms.android',
        'platforms.ios',
        'platforms.macos',
        # Optional heavy dep not on pip
        'piper',
        # Unused GUI / science stack
        'tkinter', 'PyQt5', 'PyQt6',
        'matplotlib', 'numpy', 'pandas', 'scipy',
        'cryptography',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='cleanshot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_FILE,
)
