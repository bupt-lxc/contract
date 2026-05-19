$ErrorActionPreference = "Stop"

uv sync --all-groups
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$distApp = Join-Path (Get-Location) "dist\SC GR Management"
if (Test-Path -LiteralPath $distApp) {
    Remove-Item -LiteralPath $distApp -Recurse -Force
}

uv run pyinstaller packaging/app.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
