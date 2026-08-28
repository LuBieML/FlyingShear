param(
    [string]$AppName = "ProfileCamboxGenerator",
    [switch]$OneDir
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

$VenvPython = Join-Path $Root "venv\Scripts\python.exe"
$FletExe = Join-Path $Root "venv\Scripts\flet.exe"
if (-not (Test-Path $VenvPython)) {
    throw "Project virtual environment was not found. Run build.ps1 once or create venv first."
}

& $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")

$packArgs = @(
    "pack",
    "profile_cambox_main.py",
    "--name", $AppName,
    "--distpath", (Join-Path $Root "dist"),
    "--yes"
)
if ($OneDir) {
    $packArgs += "--onedir"
}

& $FletExe @packArgs
if ($LASTEXITCODE -ne 0) {
    throw "Flet packaging failed with exit code $LASTEXITCODE"
}

Write-Host "Build complete in $(Join-Path $Root 'dist')"
