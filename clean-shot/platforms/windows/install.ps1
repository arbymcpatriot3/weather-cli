# platforms/windows/install.ps1 — Clean Shot Windows installer
# Blue Collar Nation LLC — cleanshothq.com
#
# Run in PowerShell (Admin not required):
#   iwr https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/clean-shot/platforms/windows/install.ps1 | iex
#
# Or if you have the repo:
#   powershell -ExecutionPolicy Bypass -File platforms\windows\install.ps1

$ErrorActionPreference = "Stop"

$APP_NAME    = "clean-shot"
$INSTALL_DIR = "$env:LOCALAPPDATA\$APP_NAME"
$BIN_DIR     = "$env:LOCALAPPDATA\$APP_NAME\bin"
$REPO_URL    = "https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/clean-shot"

function ok   { param($msg) Write-Host "  $(([char]0x2713))  $msg" -ForegroundColor Green }
function warn { param($msg) Write-Host "  ⚠  $msg" -ForegroundColor Yellow }
function err  { param($msg) Write-Host "  ✗  $msg" -ForegroundColor Red; exit 1 }
function info { param($msg) Write-Host "     $msg" }

Write-Host ""
Write-Host "  Clean Shot — Windows Installer" -ForegroundColor Cyan
Write-Host "  Built for the road, not the boardroom."
Write-Host "  ─────────────────────────────────────────"
Write-Host ""

# ── Find Python ────────────────────────────────────────────────────────────────
$PY = $null
$PY_CMD = $null

foreach ($candidate in @("python3", "python", "py")) {
    try {
        $ver = & $candidate --version 2>&1
        if ($ver -match "Python 3\.([89]|1[0-9])") {
            $PY = & (Get-Command $candidate -ErrorAction SilentlyContinue).Source
            $PY_CMD = $candidate
            break
        }
    } catch { }
}

if (-not $PY_CMD) {
    err "Python 3.8+ not found. Download from https://python.org and re-run this installer."
}
ok "Python found: $PY_CMD ($($ver.ToString().Trim()))"

# ── Install Python dependencies ────────────────────────────────────────────────
Write-Host ""
info "Installing Python dependencies..."
try {
    & $PY_CMD -m pip install --quiet requests colorama
    ok "Dependencies installed (requests, colorama)"
} catch {
    err "Failed to install dependencies. Try: $PY_CMD -m pip install requests colorama"
}

# ── Create install directory ───────────────────────────────────────────────────
$DIRS = @(
    "$INSTALL_DIR\core\i18n",
    "$INSTALL_DIR\display",
    "$INSTALL_DIR\platforms\windows",
    "$INSTALL_DIR\claude",
    "$INSTALL_DIR\tests",
    $BIN_DIR
)
foreach ($d in $DIRS) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}
ok "Install directory: $INSTALL_DIR"

# ── Download package files ─────────────────────────────────────────────────────
Write-Host ""
info "Downloading Clean Shot..."

$FILES = @(
    "core/__init__.py", "core/cache.py", "core/api.py", "core/parse.py",
    "core/config.py", "core/weather.py", "core/alerts.py", "core/hazards.py",
    "core/dot511.py", "core/parking.py", "core/hos.py", "core/tts.py",
    "core/gps.py", "core/subscription.py", "core/referral.py",
    "core/compress.py", "core/feedback.py", "core/health.py", "core/voice.py",
    "core/i18n/__init__.py", "core/i18n/translator.py",
    "core/i18n/en.json", "core/i18n/es.json",
    "display/__init__.py", "display/full.py", "display/route.py",
    "display/display_alerts.py", "display/glance.py",
    "display/dashboard.py", "display/themes.py",
    "platforms/__init__.py", "platforms/windows/__init__.py",
    "platforms/windows/main.py",
    "requirements.txt",
    "claude/__init__.py", "claude/prompts.py", "claude/parser.py"
)

foreach ($file in $FILES) {
    $dest = "$INSTALL_DIR\$($file -replace '/', '\')"
    $destDir = Split-Path $dest -Parent
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    try {
        Invoke-WebRequest -Uri "$REPO_URL/$file" -OutFile $dest -UseBasicParsing -ErrorAction Stop
        ok "Downloaded $file"
    } catch {
        warn "Could not download $file (skipped)"
    }
}

# ── Create cleanshot.bat launcher ──────────────────────────────────────────────
$BAT_PATH = "$BIN_DIR\cleanshot.bat"
@"
@echo off
set CLEANSHOT_CMD=cleanshot
$PY_CMD "$INSTALL_DIR\platforms\windows\main.py" %*
"@ | Set-Content -Path $BAT_PATH -Encoding ASCII
ok "Launcher created: $BAT_PATH"

# ── Add PowerShell function to profile ────────────────────────────────────────
$PS_FUNC = @"

# Clean Shot
function cleanshot { & "$PY_CMD" "$INSTALL_DIR\platforms\windows\main.py" @args }
Set-Item -Path Env:CLEANSHOT_CMD -Value "cleanshot"
"@

$PROFILE_PATH = $PROFILE
if (-not (Test-Path $PROFILE_PATH)) {
    New-Item -ItemType File -Force -Path $PROFILE_PATH | Out-Null
}

if (-not (Select-String -Path $PROFILE_PATH -Pattern "Clean Shot" -Quiet 2>$null)) {
    Add-Content -Path $PROFILE_PATH -Value $PS_FUNC
    ok "PowerShell function added to profile: $PROFILE_PATH"
} else {
    ok "PowerShell profile already configured"
}

# ── Add BIN_DIR to user PATH if not already there ────────────────────────────
$USER_PATH = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($USER_PATH -notlike "*$BIN_DIR*") {
    [Environment]::SetEnvironmentVariable("PATH", "$USER_PATH;$BIN_DIR", "User")
    $env:PATH += ";$BIN_DIR"
    ok "Added $BIN_DIR to user PATH"
} else {
    ok "$BIN_DIR already in PATH"
}

# ── Done ───────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ─────────────────────────────────────────"
ok "Clean Shot installed!"
Write-Host ""
info "In CMD:        cleanshot"
info "In PowerShell: cleanshot  (reload profile first: . `$PROFILE)"
info "Direct:        $PY_CMD $INSTALL_DIR\platforms\windows\main.py"
info "Help:          cleanshot help"
info "Check:         cleanshot doctor"
Write-Host ""
