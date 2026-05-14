param(
    [string]$AppName = "FlyingShear",
    [string]$Python = "python",
    [switch]$OneDir,
    [switch]$IncludePcmcat
)

$ErrorActionPreference = "Stop"
$env:PYTHONNOUSERSITE = "1"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"

$Root = $PSScriptRoot
Set-Location $Root

$env:PYTHONUSERBASE = Join-Path $Root ".build\python-userbase"

$VenvDir = Join-Path $Root "venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$FletExe = Join-Path $VenvDir "Scripts\flet.exe"
$Requirements = Join-Path $Root "requirements.txt"
$DistDir = Join-Path $Root "dist"
$VendorDir = Join-Path $Root ".build\trio_unifiedapi"
$SettingsFile = Join-Path $Root "setup_settings.json"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating virtual environment..."
    & $Python -m venv $VenvDir
}

Write-Host "Installing Python dependencies..."
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r $Requirements

$trioPackageDir = (& $VenvPython -c "import importlib.util, pathlib; spec = importlib.util.find_spec('Trio_UnifiedApi'); print(pathlib.Path(spec.origin).parent)").Trim()
$trioBinaries = @("Trio_UnifiedApi_TCP.dll")

if ($IncludePcmcat) {
    $trioBinaries += "Trio_UnifiedApi_PCMCAT.dll"
    $pcmcatRuntime = Join-Path $trioPackageDir "pcmcat_api_x64.dll"
    if (Test-Path $pcmcatRuntime) {
        $trioBinaries += "pcmcat_api_x64.dll"
    } else {
        Write-Warning "PCMCAT packaging requested, but pcmcat_api_x64.dll was not found next to Trio_UnifiedApi. TCP controller connections are unaffected."
    }
}

New-Item -ItemType Directory -Path $VendorDir -Force | Out-Null

foreach ($binaryName in $trioBinaries) {
    $source = Join-Path $trioPackageDir $binaryName
    if (-not (Test-Path $source)) {
        throw "Required Trio Unified API binary not found: $source"
    }
    Copy-Item -LiteralPath $source -Destination $VendorDir -Force
}

$trioBinaryArgs = @()
foreach ($binaryName in $trioBinaries) {
    $trioBinaryArgs += @("--add-binary", ".build\trio_unifiedapi\${binaryName}:.")
}

$packArgs = @(
    "pack",
    "main.py",
    "--name", $AppName,
    "--distpath", $DistDir,
    "--hidden-import", "Trio_UnifiedApi",
    "--add-data", "setup_settings.json:.",
    "--yes"
)

$packArgs += $trioBinaryArgs

if ($OneDir) {
    $packArgs += "--onedir"
}

Write-Host "Building $AppName executable..."
& $FletExe @packArgs
if ($LASTEXITCODE -ne 0) {
    throw "Flet packaging failed with exit code $LASTEXITCODE"
}

if (Test-Path $SettingsFile) {
    $settingsDestination = if ($OneDir) { Join-Path $DistDir $AppName } else { $DistDir }
    New-Item -ItemType Directory -Path $settingsDestination -Force | Out-Null
    Copy-Item -LiteralPath $SettingsFile -Destination $settingsDestination -Force
}

$exePath = if ($OneDir) {
    Join-Path (Join-Path $DistDir $AppName) "$AppName.exe"
} else {
    Join-Path $DistDir "$AppName.exe"
}

Write-Host "Build complete: $exePath"
