#Requires -Version 5.1
<#
.SYNOPSIS
    Builds CleanShotSetup.exe -- the one-click Windows installer for Clean Shot.

.DESCRIPTION
    1. Checks prerequisites (Python 3.10+, Inno Setup 6)
    2. Creates a venv and installs Python dependencies
    3. Generates the app icon + Inno Setup wizard images (Pillow)
    4. Bundles clean-shot into cleanshot.exe via PyInstaller
    5. Packages cleanshot.exe into CleanShotSetup.exe via Inno Setup

.EXAMPLE
    cd D:\weather-cli
    .\build\build_installer.ps1
#>

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# --- Paths -------------------------------------------------------------------
$BuildDir  = $PSScriptRoot                         # D:\weather-cli\build
$Root      = Split-Path -Parent $BuildDir          # D:\weather-cli
$AppDir    = Join-Path $Root   "clean-shot"        # D:\weather-cli\clean-shot
$AssetsDir = Join-Path $Root   "assets"            # D:\weather-cli\assets
$DistDir   = Join-Path $Root   "dist"              # D:\weather-cli\dist
$WorkDir   = Join-Path $Root   "build_work"        # D:\weather-cli\build_work
$VenvDir   = Join-Path $Root   ".venv-build"       # D:\weather-cli\.venv-build

$InnoExe = $null

# --- Helpers -----------------------------------------------------------------
function Step([int]$n, [int]$total, [string]$msg) {
    Write-Host ""
    Write-Host "[$n/$total] $msg" -ForegroundColor Yellow
}
function Ok([string]$msg)   { Write-Host "  OK  $msg" -ForegroundColor Green }
function Fail([string]$msg) { Write-Error "FAIL: $msg" }

# --- Step 1: Prerequisites ---------------------------------------------------
Step 1 5 "Checking prerequisites"

$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyCmd) {
    Fail "Python not found. Install Python 3.10+ from https://python.org/downloads"
}
$pyVer = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>&1
if ([version]$pyVer -lt [version]"3.10") {
    Fail "Python $pyVer found but 3.10+ is required."
}
Ok "Python $pyVer"

if (-not (Test-Path $AppDir)) {
    Fail "App source not found: $AppDir`nMake sure you are running from inside the weather-cli repo."
}
Ok "Source: $AppDir"

$innoCandidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
foreach ($p in $innoCandidates) {
    if (Test-Path $p) { $InnoExe = $p; break }
}
if (-not $InnoExe) {
    Fail "Inno Setup 6 not found.`nDownload: https://jrsoftware.org/isdl.php`nInstall, then re-run this script."
}
Ok "Inno Setup: $InnoExe"

# --- Step 2: Venv + dependencies ---------------------------------------------
Step 2 5 "Installing Python dependencies"

if (-not (Test-Path $VenvDir)) {
    Write-Host "  Creating virtual environment..."
    & python -m venv $VenvDir
}

$Pip    = Join-Path $VenvDir "Scripts\pip.exe"
$Python = Join-Path $VenvDir "Scripts\python.exe"

& $Pip install --upgrade pip --quiet
& $Pip install pyinstaller requests colorama pyttsx3 pywin32 pillow --quiet

Ok "Dependencies installed"

# --- Step 3: Generate assets -------------------------------------------------
Step 3 5 "Generating icon and wizard images"

New-Item -ItemType Directory -Force -Path $AssetsDir | Out-Null
& $Python (Join-Path $BuildDir "create_assets.py") $AssetsDir

foreach ($f in @("cleanshot.ico", "wizard_banner.bmp", "wizard_icon.bmp")) {
    if (-not (Test-Path (Join-Path $AssetsDir $f))) {
        Fail "Asset generation failed -- missing: $f"
    }
}

if (-not (Test-Path (Join-Path $AssetsDir "LICENSE.txt"))) {
    Fail "Missing assets\LICENSE.txt -- add a license file before building."
}

Ok "Assets ready in $AssetsDir"

# --- Step 4: PyInstaller -----------------------------------------------------
Step 4 5 "Bundling with PyInstaller"

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

$PyInstaller = Join-Path $VenvDir "Scripts\pyinstaller.exe"

& $PyInstaller (Join-Path $BuildDir "cleanshot.spec") --distpath $DistDir --workpath $WorkDir --noconfirm

$ExePath = Join-Path $DistDir "cleanshot.exe"
if (-not (Test-Path $ExePath)) {
    Fail "PyInstaller failed -- cleanshot.exe not found in $DistDir"
}
$ExeMB = [math]::Round((Get-Item $ExePath).Length / 1MB, 1)
Ok "cleanshot.exe (${ExeMB} MB)"

# --- Step 5: Inno Setup ------------------------------------------------------
Step 5 5 "Creating installer with Inno Setup"

& $InnoExe (Join-Path $BuildDir "setup.iss")

$SetupPath = Join-Path $DistDir "CleanShotSetup.exe"
if (-not (Test-Path $SetupPath)) {
    Fail "Inno Setup failed -- CleanShotSetup.exe not found in $DistDir"
}
$SetupMB = [math]::Round((Get-Item $SetupPath).Length / 1MB, 1)

# --- Done --------------------------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " BUILD COMPLETE" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Installer : $SetupPath"
Write-Host " Size      : ${SetupMB} MB"
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Test CleanShotSetup.exe on a fresh Windows machine"
Write-Host "  2. Verify desktop shortcut and Start Menu entry appear"
Write-Host "  3. Confirm Clean Shot launches after install"
Write-Host "  4. Upload dist\CleanShotSetup.exe to your download page"
Write-Host ""
