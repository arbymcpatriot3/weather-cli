@echo off
REM platforms/windows/cleanshot.bat — Clean Shot Windows launcher
REM Place this file anywhere in your PATH or Desktop.
REM TODO: update INSTALL_DIR to match your install location

set INSTALL_DIR=%USERPROFILE%\Documents\CleanShot
set CLEANSHOT_CMD=cleanshot

REM Set minimum console size — 120 cols x 50 lines
mode con: cols=120 lines=50

python "%INSTALL_DIR%\clean-shot\platforms\windows\main.py" %*
