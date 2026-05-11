# Run backend pytest suite (Windows). Use -Slow to also run real Kokoro tests.
param(
    [switch]$Slow
)
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Here "backend")

if (-not (Test-Path ".venv")) {
    Write-Error "No .venv yet; run scripts/setup_backend.ps1 first."
    exit 1
}

$venvPython = ".\.venv\Scripts\python.exe"
if ($Slow) {
    & $venvPython -m pytest -v
} else {
    & $venvPython -m pytest -m "not slow" -v
}
