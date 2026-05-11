# Full local end-to-end verification on Windows.
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $PSScriptRoot
Set-Location $Here

Write-Host "=== environment check ===" -ForegroundColor Cyan
$venvPython = Join-Path $Here "backend\.venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    & $venvPython "$Here\scripts\check_environment.py"
} else {
    & py -3.12 "$Here\scripts\check_environment.py"
}

Write-Host "=== backend setup ===" -ForegroundColor Cyan
& powershell -ExecutionPolicy Bypass -File "$Here\scripts\setup_backend.ps1"

Write-Host "=== frontend setup ===" -ForegroundColor Cyan
& powershell -ExecutionPolicy Bypass -File "$Here\scripts\setup_frontend.ps1"

Write-Host "=== backend tests (fast) ===" -ForegroundColor Cyan
& powershell -ExecutionPolicy Bypass -File "$Here\scripts\run_tests.ps1"

Write-Host "=== frontend build ===" -ForegroundColor Cyan
Push-Location (Join-Path $Here "frontend")
npm run build
Pop-Location

Write-Host "=== starting backend in mock mode ===" -ForegroundColor Cyan
$env:APP_MODE = "mock"
$backendCmd = "Set-Location '$($Here -replace "'","''")\backend'; `$env:APP_MODE='mock'; `$env:BACKEND_PORT='8000'; `$env:BACKEND_HOST='127.0.0.1'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
$backend = Start-Process -PassThru -FilePath "powershell" -ArgumentList "-NoProfile","-Command",$backendCmd

# Wait for health
for ($i = 0; $i -lt 30; $i++) {
    try {
        $r = Invoke-RestMethod "http://127.0.0.1:8000/api/health" -TimeoutSec 2
        if ($r.status -eq "ok") { break }
    } catch {
        Start-Sleep -Seconds 1
    }
}

Write-Host "=== starting frontend ===" -ForegroundColor Cyan
$frontendCmd = "Set-Location '$($Here -replace "'","''")\frontend'; npm run dev"
$frontend = Start-Process -PassThru -FilePath "powershell" -ArgumentList "-NoProfile","-Command",$frontendCmd

# Wait for frontend
$frontendUrl = "http://127.0.0.1:3000"
for ($i = 0; $i -lt 60; $i++) {
    try {
        $r = Invoke-WebRequest $frontendUrl -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { break }
    } catch {
        try {
            $r = Invoke-WebRequest "http://127.0.0.1:3001" -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) { $frontendUrl = "http://127.0.0.1:3001"; break }
        } catch {}
        Start-Sleep -Seconds 1
    }
}

Write-Host "Frontend URL: $frontendUrl" -ForegroundColor Cyan

try {
    Write-Host "=== Playwright e2e ===" -ForegroundColor Cyan
    Push-Location (Join-Path $Here "frontend")
    npx playwright install chromium
    $env:E2E_BASE_URL = $frontendUrl
    npx playwright test
    Pop-Location
} finally {
    Write-Host "=== shutting down ===" -ForegroundColor Cyan
    if ($backend -and -not $backend.HasExited) { Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue }
    if ($frontend -and -not $frontend.HasExited) { Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue }
}

Write-Host "=== DONE ===" -ForegroundColor Green
