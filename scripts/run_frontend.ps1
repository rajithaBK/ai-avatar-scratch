# Run the Vite dev server on Windows.
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Here "frontend")
npm run dev
