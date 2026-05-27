$ErrorActionPreference = "Stop"

# ============================================
# SC GR Management — Dev Mode Launcher
# Uses local database for offline development
# ============================================
$env:SC_GR_DEV = "1"

Push-Location (Join-Path $PSScriptRoot)
$projectRoot = Get-Location

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " SC GR Management — DEV MODE" -ForegroundColor Cyan
Write-Host " Database: %APPDATA%\sc-gr-management-dev" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Start Vite dev server in background
Write-Host "Starting Vite dev server..." -ForegroundColor Yellow
$viteJob = Start-Job -ArgumentList $projectRoot -ScriptBlock {
    param($root)
    Set-Location (Join-Path $root "frontend")
    npm run dev 2>&1 | Out-Null
}

# Wait for Vite to be ready
Write-Host "Waiting for Vite to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 4

try {
    Write-Host "Launching app..." -ForegroundColor Green
    uv run python -m sc_gr_app.main
} finally {
    Stop-Job -Job $viteJob
    Remove-Job -Job $viteJob
    Pop-Location
}
