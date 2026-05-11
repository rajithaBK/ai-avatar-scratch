# Run the FastAPI backend on Windows.
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Here "backend")

if (-not (Test-Path ".venv")) {
    Write-Error "No .venv yet; run scripts/setup_backend.ps1 first."
    exit 1
}

# Load .env if present
$envFile = Join-Path $Here ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
        }
    }
}

$port = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8000" }
$host_ = if ($env:BACKEND_HOST) { $env:BACKEND_HOST } else { "0.0.0.0" }

Write-Host "Starting backend on $($host_):$port (APP_MODE=$($env:APP_MODE))" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host $host_ --port $port
