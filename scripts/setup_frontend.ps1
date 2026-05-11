# Set up frontend dependencies (Windows).
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Here "frontend")
npm install
Write-Host "[setup] Frontend deps installed." -ForegroundColor Green
Write-Host "[setup] To install Playwright browsers run: npx playwright install chromium"
