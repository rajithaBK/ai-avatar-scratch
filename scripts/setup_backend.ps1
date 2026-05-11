# Set up the backend Python virtualenv and install dependencies. (Windows)
$ErrorActionPreference = "Stop"

$Here = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Here "backend")

$Py = $env:PYTHON
if (-not $Py) {
    if (Get-Command "py" -ErrorAction SilentlyContinue) {
        $Py = "py -3.12"
    } else {
        $Py = "python"
    }
}

Write-Host "[setup] Using Python: $Py" -ForegroundColor Cyan
& cmd /c "$Py --version"

if (-not (Test-Path ".venv")) {
    & cmd /c "$Py -m venv .venv"
}

$venvPython = ".\.venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

Write-Host "[setup] Backend dependencies installed." -ForegroundColor Green
Write-Host "[setup] Note: real MuseTalk inference requires the MuseTalk repo + weights."
Write-Host "        See README.md for the full instructions."
