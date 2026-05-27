$ErrorActionPreference = "Stop"

Push-Location (Join-Path $PSScriptRoot "..")

# 1. Build Vue frontend
Write-Host "=== Building Vue frontend ===" -ForegroundColor Cyan
Push-Location frontend
npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; Pop-Location; exit $LASTEXITCODE }
Pop-Location

# 2. Install Python dependencies
Write-Host "=== Installing Python dependencies ===" -ForegroundColor Cyan
uv sync --all-groups
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }

# 3. Run tests
Write-Host "=== Running tests ===" -ForegroundColor Cyan
uv run pytest -q
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }

# 4. Clean old dist
$distDir = Join-Path (Get-Location) "dist"
$distApp = Join-Path $distDir "SC GR Management"
if (Test-Path -LiteralPath $distApp) {
    Remove-Item -LiteralPath $distApp -Recurse -Force
}

# 5. Build executable
Write-Host "=== Building with PyInstaller ===" -ForegroundColor Cyan
uv run pyinstaller packaging/app.spec
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }

Write-Host "=== Done ===" -ForegroundColor Green
Write-Host "Output: $distApp"

Pop-Location
