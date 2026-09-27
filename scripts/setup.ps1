[CmdletBinding()]
param(
    [string]$PythonVersion = "3.11",
    [switch]$SkipPrerequisiteChecks
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$VenvDir = Join-Path $ProjectDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$RequirementsFile = Join-Path $ProjectDir "requirements.txt"
$EnvTemplate = Join-Path $ProjectDir ".env.template"
$EnvFile = Join-Path $ProjectDir ".env"

Set-Location $ProjectDir

function Test-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-PythonLauncher {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & py "-$PythonVersion" @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE."
    }
}

Write-Host "Setting up JARVIS for Windows..." -ForegroundColor Cyan

if (-not (Test-Command "py")) {
    throw "The Python launcher ('py') was not found. Install Python $PythonVersion from python.org and enable the launcher."
}

Invoke-PythonLauncher -Arguments @("-c", "import sys; expected='$PythonVersion'; actual=f'{sys.version_info.major}.{sys.version_info.minor}'; assert actual == expected, f'Expected Python {expected}, found {actual}'")

if (-not $SkipPrerequisiteChecks) {
    $MissingTools = @()
    foreach ($Tool in @("cmake", "ffmpeg")) {
        if (-not (Test-Command $Tool)) {
            $MissingTools += $Tool
        }
    }

    if ($MissingTools.Count -gt 0) {
        Write-Warning "Optional/native build tools missing from PATH: $($MissingTools -join ', ')."
        Write-Warning "Install CMake and FFmpeg before retrying if dlib, face-recognition, or audio packages fail."
    }
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating virtual environment at $VenvDir..."
    Invoke-PythonLauncher -Arguments @("-m", "venv", $VenvDir)
} else {
    Write-Host "Reusing existing virtual environment at $VenvDir."
}

Write-Host "Upgrading packaging tools..."
& $VenvPython -m pip install --upgrade pip "setuptools<81" wheel
if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade packaging tools." }

if (-not (Test-Path $RequirementsFile)) {
    throw "requirements.txt was not found at $RequirementsFile"
}

Write-Host "Installing Python dependencies..."
& $VenvPython -m pip install -r $RequirementsFile
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

if (-not (Test-Path $EnvFile) -and (Test-Path $EnvTemplate)) {
    Copy-Item $EnvTemplate $EnvFile
    Write-Host "Created .env from .env.template. Add your provider credentials before running JARVIS." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "JARVIS setup completed successfully." -ForegroundColor Green
Write-Host "Activate the environment with:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "Or run JARVIS directly with:"
Write-Host "  .\.venv\Scripts\python.exe -m src.jarvis_v2"
