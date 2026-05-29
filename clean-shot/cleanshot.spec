# -*- mode: python ; coding: utf-8 -*-
# Clean Shot — PyInstaller spec
# display.full etc. are injected into a.pure directly via importlib so they
# end up in the PYZ as compiled modules regardless of analysis path quirks.
#
# Build: cd CleanShot && pyinstaller clean-shot/cleanshot.spec

import sys, os, importlib.util
# SPECPATH is the directory containing this spec file (clean-shot/)
sys.path.insert(0, SPECPATH)

_LOCAL_MODULES = [
    'display', 'display.full', 'display.display_alerts', 'display.route',
    'display.replaces', 'display.glance', 'display.themes', 'display.dashboard',
    'core', 'core.weather', 'core.config', 'core.api', 'core.cache',
    'core.alerts', 'core.tts', 'core.gps', 'core.parse', 'core.hazards',
    'core.dot511', 'core.parking', 'core.hos', 'core.subscription',
    'core.referral', 'core.updater', 'core.feedback', 'core.voice',
    'core.i18n', 'core.i18n.translator',
    'claude', 'claude.prompts', 'claude.parser', 'claude.patterns', 'claude.digest',
    'platforms', 'platforms.windows',
    'platforms.windows.tts_windows', 'platforms.windows.gps_windows',
]

a = Analysis(
    [os.path.join(SPECPATH, 'platforms', 'windows', 'main.py')],
    pathex=[SPECPATH],
    binaries=[],
    datas=[
        (os.path.join(SPECPATH, 'core', 'i18n', 'en.json'), 'core/i18n'),
        (os.path.join(SPECPATH, 'core', 'i18n', 'es.json'), 'core/i18n'),
    ],
    hiddenimports=[
        'win32com.client', 'win32com.server.policy', 'colorama', 'requests',
    ] + _LOCAL_MODULES,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Inject/replace local modules in a.pure so they land in the PYZ correctly.
# The analysis may have found display/__init__.py but stored it with the wrong
# path or without package context, causing is_package=0 at archive-write time.
# We remove any existing entry and re-insert with the confirmed __init__.py path
# so the archive writer sees src_basename=='__init__' and sets PYZ_ITEM_PKG.
_to_remove = {modname for modname in _LOCAL_MODULES}
a.pure[:] = [(n, p, t) for n, p, t in a.pure if n not in _to_remove]

for modname in _LOCAL_MODULES:
    spec = importlib.util.find_spec(modname)
    if spec and spec.origin and spec.origin.endswith('.py'):
        a.pure.append((modname, spec.origin, 'PYMODULE'))

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='cleanshot',
    icon=os.path.join(SPECPATH, '..', 'assets', 'cleanshot.ico'),
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
)
