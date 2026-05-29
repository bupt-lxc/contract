$ErrorActionPreference = "Stop"

# ============================================
# SC GR Management -- Dev Mode Launcher
# Uses local database for offline development
# ============================================
$env:SC_GR_DEV = "1"

Push-Location $PSScriptRoot
$projectRoot = Get-Location
$env:SC_GR_DATA_DIR = $projectRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " SC GR Management -- DEV MODE" -ForegroundColor Cyan
Write-Host " Database: $projectRoot\data\sc_gr.sqlite3" -ForegroundColor Cyan
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
