@echo off
REM platforms/windows/cleanshot.bat — Clean Shot Windows launcher
REM Place this file anywhere in your PATH or Desktop.
REM TODO: update INSTALL_DIR to match your install location

set INSTALL_DIR=%USERPROFILE%\AppData\Local\clean-shot
set CLEANSHOT_CMD=cleanshot
python "%INSTALL_DIR%\platforms\windows\main.py" %*
