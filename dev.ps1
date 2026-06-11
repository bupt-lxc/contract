$ErrorActionPreference = "Stop"

# ============================================
# PO Management Platform -- Dev Mode Launcher
# Uses local database for offline development
# ============================================
$env:SC_GR_DEV = "1"

Push-Location $PSScriptRoot
$projectRoot = Get-Location
$env:SC_GR_DATA_DIR = $projectRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " PO Management Platform -- DEV MODE" -ForegroundColor Cyan
Write-Host " Database: $projectRoot\data\sc_gr.sqlite3" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Start Vite dev server in background
Write-Host "Starting Vite dev server..." -ForegroundColor Yellow
$viteJob = Start-Job -ArgumentList $projectRoot -ScriptBlock {
    param($root)
    Set-Location (Join-Path $root "frontend")
    npm run dev 2>&1 | Out-Null
}

# Start notification script in background (draft mode — saves to Drafts folder)
Write-Host "Starting email notification script (draft mode)..." -ForegroundColor Yellow
$notifyJob = Start-Job -ArgumentList $projectRoot -ScriptBlock {
    param($root)
    Set-Location $root
    $env:SC_GR_DEV = "1"
    $env:SC_GR_DATA_DIR = $root
    uv run python -m sc_gr_app.notification --draft --poll-interval 60 2>&1 | Out-Null
}

# Wait for Vite to be ready
Write-Host "Waiting for Vite to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 4

try {
    Write-Host "Launching app..." -ForegroundColor Green
    uv run python -m sc_gr_app.main
} finally {
    Stop-Job -Job $viteJob -ErrorAction SilentlyContinue
    Remove-Job -Job $viteJob -ErrorAction SilentlyContinue
    Stop-Job -Job $notifyJob -ErrorAction SilentlyContinue
    Remove-Job -Job $notifyJob -ErrorAction SilentlyContinue
    Pop-Location
}
