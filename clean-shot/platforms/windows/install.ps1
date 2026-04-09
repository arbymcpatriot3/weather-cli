# platforms/windows/install.ps1 — Clean Shot Windows Installer
# Blue Collar Nation LLC — cleanshothq.com
#
# One-line install in PowerShell (no admin required):
#   iwr -useb https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/clean-shot/platforms/windows/install.ps1 | iex

# Suppress PowerShell's own error formatting — we handle all errors ourselves
$ErrorActionPreference = "SilentlyContinue"
trap { }

$INSTALL_DIR = "$env:USERPROFILE\Documents\CleanShot"
$BIN_DIR     = "$env:USERPROFILE\AppData\Local\Microsoft\WindowsApps"

function ok   { param($m) Write-Host "  [OK]  $m" -ForegroundColor Green }
function warn { param($m) Write-Host "  [!]   $m" -ForegroundColor Yellow }
function info { param($m) Write-Host "        $m" }
function die  {
    param($m)
    Write-Host ""
    Write-Host "  [ERR] $m" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Need help? support@cleanshothq.com" -ForegroundColor Cyan
    Write-Host "  cleanshothq.com" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

function Refresh-Path {
    $m = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    $u = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $env:PATH = "$m;$u"
}

# ── Header ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  Clean Shot — Windows Installer       " -ForegroundColor Cyan
Write-Host "  Built for the road, not the boardroom"
Write-Host "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host ""

# ── STEP 1: Safety check — never run from System32 ────────────────────────────
$here = (Get-Location).Path
if ($here -like "*System32*" -or $here -like "*system32*") {
    warn "Running from System32 — switching to safe location..."
    Set-Location "$env:USERPROFILE\Documents"
    ok "Switched to: $env:USERPROFILE\Documents"
}

# ── STEP 2: Find or install Python ────────────────────────────────────────────
info "Checking Python..."
$pyExe  = $null
$pyArgs = @()

# Check for Python 3.14 (known WinError 123 crash on Windows)
$py314 = & py -3.14 --version 2>&1
if ("$py314" -match "3\.14") {
    warn "Python 3.14 detected — has a known crash on Windows (WinError 123)."
    info "Installing Python 3.11 (stable)..."
    winget install Python.Python.3.11 --exact --silent `
        --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
    Refresh-Path
}

# Try py launcher with explicit 3.11
$v = & py -3.11 --version 2>&1
if ("$v" -match "Python 3\.11") { $pyExe = "py"; $pyArgs = @("-3.11") }

# Try py launcher with any compatible version
if (-not $pyExe) {
    $v = & py --version 2>&1
    if ("$v" -match "Python 3\.(8|9|10|11|12|13)(\.|$)") {
        $pyExe = "py"; $pyArgs = @()
    }
}

# Try python3 / python
if (-not $pyExe) {
    foreach ($cmd in @("python3", "python")) {
        $v = & $cmd --version 2>&1
        if ("$v" -match "Python 3\.(8|9|10|11|12|13)(\.|$)") {
            $pyExe = $cmd; $pyArgs = @(); break
        }
    }
}

# Still nothing — install via winget
if (-not $pyExe) {
    info "Python not found. Installing Python 3.11..."
    $wr = winget install Python.Python.3.11 --exact --silent `
        --accept-source-agreements --accept-package-agreements 2>&1
    Refresh-Path
    $v = & py -3.11 --version 2>&1
    if ("$v" -match "Python 3\.11") {
        $pyExe = "py"; $pyArgs = @("-3.11")
        ok "Python 3.11 installed"
    } else {
        die "Python install failed.`n  Visit https://python.org — install Python 3.11, then re-run this installer."
    }
} else {
    $vShow = & $pyExe ($pyArgs + @("--version")) 2>&1
    ok "Python: $("$vShow".Trim())"
}

# ── STEP 3: Find or install Git ───────────────────────────────────────────────
info "Checking Git..."
$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
    info "Git not found. Installing..."
    winget install Git.Git --exact --silent `
        --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
    Refresh-Path
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) {
        die "Git install failed.`n  Visit https://git-scm.com — install Git, then re-run this installer."
    }
    ok "Git installed"
} else {
    ok "Git found"
}

# ── STEP 4: Clone or update repo ──────────────────────────────────────────────
Write-Host ""
info "Setting up Clean Shot..."
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\Documents" | Out-Null

if (Test-Path "$INSTALL_DIR\clean-shot\platforms\windows\main.py") {
    info "Updating existing installation..."
    git -C "$INSTALL_DIR" pull --quiet 2>&1 | Out-Null
    ok "Updated to latest version"
} else {
    info "Downloading Clean Shot (this takes about 10 seconds)..."
    # Remove partial clone if present
    if (Test-Path "$INSTALL_DIR") {
        Remove-Item -Recurse -Force "$INSTALL_DIR" -ErrorAction SilentlyContinue
    }
    git clone "https://github.com/arbymcpatriot3/weather-cli.git" "$INSTALL_DIR" 2>&1 | Out-Null
    if (-not (Test-Path "$INSTALL_DIR\clean-shot\platforms\windows\main.py")) {
        die "Download failed. Check your internet connection and try again."
    }
    ok "Clean Shot downloaded to: $INSTALL_DIR"
}

# ── STEP 5: Install Python packages ───────────────────────────────────────────
Write-Host ""
info "Installing Python packages..."
& $pyExe ($pyArgs + @("-m", "pip", "install", "requests", "colorama", "--quiet")) 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    ok "Packages installed (requests, colorama)"
} else {
    warn "Package install had issues. If the app fails, run:"
    warn "  & $pyExe $($pyArgs -join ' ') -m pip install requests colorama"
}

# ── STEP 6: Create cleanshot.bat launcher ─────────────────────────────────────
New-Item -ItemType Directory -Force -Path $BIN_DIR | Out-Null
$batPath = "$BIN_DIR\cleanshot.bat"
$batLines = "@echo off", "cd /d `"$INSTALL_DIR\clean-shot`"", "$pyExe $($pyArgs -join ' ') platforms\windows\main.py %*"
[System.IO.File]::WriteAllText($batPath, ($batLines -join "`r`n") + "`r`n", [System.Text.Encoding]::ASCII)
ok "Launcher: $batPath"

# ── STEP 7: Add PowerShell function to profile ────────────────────────────────
$profilePath = $PROFILE
if (-not $profilePath) { $profilePath = "$env:USERPROFILE\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1" }
$profileDir  = Split-Path $profilePath -Parent
if (-not (Test-Path $profileDir)) { New-Item -ItemType Directory -Force -Path $profileDir | Out-Null }
if (-not (Test-Path $profilePath)) { New-Item -ItemType File -Force -Path $profilePath | Out-Null }

$alreadySet = Select-String -Path $profilePath -Pattern "Clean Shot" -Quiet 2>&1
if (-not $alreadySet) {
    $escapedDir = $INSTALL_DIR -replace '\\', '\\'
    $psFunc = @"

# Clean Shot
function cleanshot {
    Push-Location "$INSTALL_DIR\clean-shot"
    & $pyExe $($pyArgs -join ' ') platforms\windows\main.py `$args
    Pop-Location
}
"@
    Add-Content -Path $profilePath -Value $psFunc
    ok "PowerShell function added to: $profilePath"
} else {
    ok "PowerShell profile already configured"
}

# ── STEP 8: Run doctor ────────────────────────────────────────────────────────
Write-Host ""
info "Running system check..."
Push-Location "$INSTALL_DIR\clean-shot"
$doctor = & $pyExe ($pyArgs + @("platforms\windows\main.py", "doctor")) 2>&1
Pop-Location
if ($doctor) {
    $doctor | ForEach-Object { info "$_" }
}

# ── STEP 9: Success ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host "  OK  Clean Shot installed!" -ForegroundColor Green
Write-Host ""
Write-Host "  Open a NEW PowerShell window and type:" -ForegroundColor White
Write-Host "    cleanshot" -ForegroundColor Cyan
Write-Host ""
info "For help:      cleanshot help"
info "Check system:  cleanshot doctor"
info ""
info "Need help?     support@cleanshothq.com"
info "               cleanshothq.com"
Write-Host "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host ""
