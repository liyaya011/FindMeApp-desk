# PowerShell build script for FindMeApp (Windows)
# Usage:
#   .\build.ps1                # Build .exe
#   .\build.ps1 -Clean         # Clean build
#   .\build.ps1 -SkipModel     # Skip model bundling (faster testing)

param(
    [switch]$Clean = $false,
    [switch]$SkipModel = $false
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path "$PSScriptRoot"

Write-Host "===== FindMeApp Windows Build =====" -ForegroundColor Cyan
Write-Host "Project root: $Root"

# --- 1. Verify venv --------------------------------------------------------
$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv "$Root\.venv"
}
& $venvPython -m pip install --upgrade pip | Out-Null

# --- 2. Install deps --------------------------------------------------------
$reqPath = Join-Path $Root "requirements.txt"
if (Test-Path $reqPath) {
    Write-Host "Installing requirements..." -ForegroundColor Yellow
    & $venvPython -m pip install -r $reqPath
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
}

# Ensure PyInstaller is available
& $venvPython -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $venvPython -m pip install pyinstaller
}

# --- 3. Prepare model files ------------------------------------------------
$modelDir = Join-Path $Root "assets\models\buffalo_l"
if (-not (Test-Path $modelDir)) {
    if ($SkipModel) {
        Write-Host "WARNING: Model not found and -SkipModel set; .exe will require download on first run." -ForegroundColor Yellow
    } else {
        Write-Host "Downloading insightface buffalo_l model..." -ForegroundColor Yellow
        # Use insightface's built-in downloader
        & $venvPython -c @"
from insightface.utils import ensure_available
ensure_available('models', 'buffalo_l', root='$Root\assets')
"@
        if ($LASTEXITCODE -ne 0) { throw "Model download failed" }
    }
} else {
    Write-Host "Model already present at $modelDir"
}

# --- 4. Build ---------------------------------------------------------------
$distDir = Join-Path $Root "dist"
$buildDir = Join-Path $Root "build"
if ($Clean) {
    Write-Host "Cleaning previous build..." -ForegroundColor Yellow
    if (Test-Path $distDir) { Remove-Item -Recurse -Force $distDir }
    if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir }
}

Write-Host "Running PyInstaller..." -ForegroundColor Yellow
Push-Location $Root
try {
    & $venvPython -m PyInstaller build.spec --noconfirm
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
} finally {
    Pop-Location
}

# --- 5. Verify --------------------------------------------------------------
$outExe = Join-Path $distDir "FindMeApp\FindMeApp.exe"
if (Test-Path $outExe) {
    $size = (Get-Item $outExe).Length / 1MB
    Write-Host "Build successful!" -ForegroundColor Green
    Write-Host "  Output: $outExe"
    Write-Host "  Size:   $([math]::Round($size,1)) MB"
} else {
    throw "Build output not found: $outExe"
}

# Verify model files are included
$bundledModels = Get-ChildItem -Path (Join-Path $distDir "FindMeApp") -Filter "*.onnx" -Recurse -ErrorAction SilentlyContinue
if ($bundledModels) {
    Write-Host "  Bundled models: $($bundledModels.Count) .onnx files"
} else {
    Write-Host "  WARNING: No .onnx files found in bundle!" -ForegroundColor Yellow
}
