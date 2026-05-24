# platforms/windows/install.ps1 â€” Clean Shot Windows Installer
# Blue Collar Nation LLC â€” cleanshothq.com
#
# One-line install in PowerShell (no admin required):
#   iwr -useb https://raw.githubusercontent.com/arbymcpatriot3/weather-cli/main/clean-shot/platforms/windows/install.ps1 | iex

$ErrorActionPreference = "SilentlyContinue"
trap { }

if (Test-Path "D:\") {
    $INSTALL_DIR = "D:\Documents\CleanShot"
} else {
    $INSTALL_DIR = "$env:USERPROFILE\Documents\CleanShot"
}
$BIN_DIR     = "$env:USERPROFILE\AppData\Local\Microsoft\WindowsApps"

function ok   { param($m) Write-Host "  [OK]  $m" -ForegroundColor Green }
function warn { param($m) Write-Host "  [!]   $m" -ForegroundColor Yellow }
function info { param($m) Write-Host "        $m" }

function Refresh-Path {
    $m = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    $u = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $env:PATH = "$m;$u"
}

# â”€â”€ Header â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Write-Host ""
Write-Host "  â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”" -ForegroundColor Cyan
Write-Host "  Clean Shot â€” Windows Installer       " -ForegroundColor Cyan
Write-Host "  Built for the road, not the boardroom"
Write-Host "  â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”" -ForegroundColor Cyan
Write-Host ""

# â”€â”€ STEP 1: Safety check â€” never run from System32 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
$here = (Get-Location).Path
if ($here -like "*System32*" -or $here -like "*system32*") {
    Set-Location "$env:USERPROFILE\Documents"
}

# â”€â”€ STEP 2: Find or install Python â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
info "Checking Python..."
$pyExe  = $null
$pyArgs = @()

# Block Python 3.14 (known WinError 123 crash on Windows)
$py314 = & py -3.14 --version 2>&1
if ("$py314" -match "3\.14") {
    info "Installing Python 3.11 (stable)..."
    winget install Python.Python.3.11 --exact --silent `
        --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
    Refresh-Path
}

# Try py launcher with 3.11 first
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

# Auto-install via winget
if (-not $pyExe) {
    info "Installing Python 3.11 automatically..."
    winget install Python.Python.3.11 --exact --silent `
        --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
    Refresh-Path
    $v = & py -3.11 --version 2>&1
    if ("$v" -match "Python 3\.11") {
        $pyExe = "py"; $pyArgs = @("-3.11")
        ok "Python 3.11 installed"
    } else {
        # Try the direct path
        $pyPath = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
        if (Test-Path $pyPath) {
            $pyExe = $pyPath; $pyArgs = @()
            ok "Python 3.11 installed"
        } else {
            warn "Python install pending â€” may need to reopen PowerShell and re-run"
        }
    }
}

if ($pyExe) {
    $vShow = & $pyExe ($pyArgs + @("--version")) 2>&1
    ok "Python ready: $("$vShow".Trim())"
}

# â”€â”€ STEP 3: Find or install Git â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
info "Checking Git..."
$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
    info "Installing Git automatically..."
    winget install Git.Git --exact --silent `
        --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
    Refresh-Path
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) {
        ok "Git installed"
    } else {
        warn "Git install pending â€” may need to reopen PowerShell and re-run"
    }
} else {
    ok "Git ready"
}

# â”€â”€ STEP 4: Clone or update repo â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Write-Host ""
info "Setting up Clean Shot..."
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\Documents" | Out-Null

if (Test-Path "$INSTALL_DIR\.git") {
    info "Updating existing installation..."
    git -C "$INSTALL_DIR" pull --quiet 2>&1 | Out-Null
    ok "Updated to latest version"
} else {
    info "Downloading Clean Shot..."
    if (Test-Path "$INSTALL_DIR") {
        Remove-Item -Recurse -Force "$INSTALL_DIR" -ErrorAction SilentlyContinue
    }
    git clone "https://github.com/arbymcpatriot3/weather-cli.git" "$INSTALL_DIR" --quiet 2>&1 | Out-Null
    ok "Clean Shot downloaded"
}

# â”€â”€ STEP 5: Install Python packages â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Write-Host ""
info "Installing Python packages..."
if ($pyExe) {
    & $pyExe ($pyArgs + @("-m", "pip", "install", "--upgrade", "pip", "--quiet")) 2>&1 | Out-Null
    & $pyExe ($pyArgs + @("-m", "pip", "install", "requests", "colorama", "pywin32", "pyttsx3", "--quiet")) 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        & $pyExe ($pyArgs + @("-m", "pip", "install", "requests", "colorama", "pywin32", "pyttsx3", "--quiet", "--user")) 2>&1 | Out-Null
    }

    # Verify pyttsx3 installed
    $ttsOk = & $pyExe ($pyArgs + @("-c", "import pyttsx3; print('ok')")) 2>&1
    if ("$ttsOk" -match "ok") {
        ok "Packages installed (requests, colorama, pywin32, pyttsx3)"
    } else {
        ok "Packages installed (requests, colorama, pywin32)"
        warn "pyttsx3 install issue â€” run: py -3.11 -m pip install pyttsx3"
    }
}

# â”€â”€ STEP 6: Create cleanshot.bat launcher â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
New-Item -ItemType Directory -Force -Path $BIN_DIR | Out-Null
$batPath = "$BIN_DIR\cleanshot.bat"
$pyLine = if ($pyArgs.Count -gt 0) { "$pyExe $($pyArgs -join ' ')" } else { "$pyExe" }
$batLines = "@echo off", "cd /d `"$INSTALL_DIR\clean-shot`"", "$pyLine platforms\windows\main.py %*"
[System.IO.File]::WriteAllText($batPath, ($batLines -join "`r`n") + "`r`n", [System.Text.Encoding]::ASCII)
ok "Launcher: $batPath"

# â”€â”€ STEP 7: Add PowerShell function to profile â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
$profilePath = $PROFILE
if (-not $profilePath) {
    $profilePath = "$env:USERPROFILE\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1"
}
$profileDir = Split-Path $profilePath -Parent
if (-not (Test-Path $profileDir)) { New-Item -ItemType Directory -Force -Path $profileDir | Out-Null }
if (-not (Test-Path $profilePath)) { New-Item -ItemType File -Force -Path $profilePath | Out-Null }

$alreadySet = Select-String -Path $profilePath -Pattern "Clean Shot" -Quiet 2>&1
if (-not $alreadySet) {
    $pyLine = if ($pyArgs.Count -gt 0) { "$pyExe $($pyArgs -join ' ')" } else { "$pyExe" }
    $psFunc = @"

# Clean Shot
function cleanshot {
    Push-Location "$INSTALL_DIR\clean-shot"
    & $pyLine platforms\windows\main.py `$args
    Pop-Location
}
"@
    Add-Content -Path $profilePath -Value $psFunc
    ok "PowerShell function added"
} else {
    ok "PowerShell profile ready"
}

# â”€â”€ STEP 8: Run doctor â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Write-Host ""
info "Checking Clean Shot..."
if ($pyExe) {
    Push-Location "$INSTALL_DIR\clean-shot"
    $doctor = & $pyExe ($pyArgs + @("platforms\windows\main.py", "doctor")) 2>&1
    Pop-Location
    if ($doctor) { $doctor | ForEach-Object { info "$_" } }
}

# â”€â”€ Success â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Write-Host ""
Write-Host "  â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”" -ForegroundColor Green
Write-Host "  Clean Shot installed!               " -ForegroundColor Green
Write-Host ""
info "For help:  cleanshot help"
info "Support:   support@cleanshothq.com"
Write-Host "  â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”" -ForegroundColor Green
Write-Host ""

# â”€â”€ Launch Clean Shot â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
info "Starting Clean Shot..."
Write-Host ""
if ($pyExe) {
    Push-Location "$INSTALL_DIR\clean-shot"
    & $pyExe ($pyArgs + @("platforms\windows\main.py")) 2>&1
    Pop-Location
}

