$ErrorActionPreference = "Stop"

Push-Location (Join-Path $PSScriptRoot "..")

$sharedDrive = "\\ap.vwg\fileshare\AUDI CHINA\Audi_China_RnD\R&D\EG\10_EG-V\80000_EG_W\DMAS\01 Daily working files\contract"
Write-Host "Shared drive: $sharedDrive" -ForegroundColor Cyan

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

# 6. Build Inno Setup installer
$iscc = Join-Path $env:USERPROFILE "Utils\InnoSetup6\ISCC.exe"
if (Test-Path $iscc) {
    Write-Host "=== Building installer with Inno Setup ===" -ForegroundColor Cyan
    & $iscc packaging/setup.iss
    if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
} else {
    Write-Host "=== Skipping Inno Setup (not found) ===" -ForegroundColor Yellow
}

# 7. Build notification executable
Write-Host "=== Building notification executable ===" -ForegroundColor Cyan
uv run pyinstaller packaging/notification.spec --distpath $distDir --workpath (Join-Path $distDir "build-notification") --noconfirm
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }

# Rename notification output to include version
$version = (uv run python -c "from sc_gr_app import __version__; print(__version__)").Trim()
$notifySrcDir = Join-Path $distDir "SC-GR-Notification"
$notifySrcExe = Join-Path $notifySrcDir "SC-GR-Notification.exe"
$notifyDstExe = Join-Path $distDir "SC-GR-Notification-$version.exe"
Copy-Item $notifySrcExe $notifyDstExe
Write-Host "Notification executable: $notifyDstExe" -ForegroundColor Green

# 8. Push to shared drive (only if shared drive is accessible)
$sharedReleases = Join-Path $sharedDrive "releases"
$guiInstaller = "SC-GR-Management-$version-Setup.exe"
$notifyExe = "SC-GR-Notification-$version.exe"

Write-Host "=== Pushing to shared drive ===" -ForegroundColor Cyan
if (-not (Test-Path $sharedReleases)) {
    New-Item -ItemType Directory -Path $sharedReleases -Force | Out-Null
}

# Copy files
Copy-Item -Path (Join-Path $distDir "installer" $guiInstaller) -Destination $sharedReleases -Force
Copy-Item -Path (Join-Path $distDir $notifyExe) -Destination $sharedReleases -Force

# Compute SHA256
$guiHash = (Get-FileHash -Path (Join-Path $sharedReleases $guiInstaller) -Algorithm SHA256).Hash.ToLower()
$notifyHash = (Get-FileHash -Path (Join-Path $sharedReleases $notifyExe) -Algorithm SHA256).Hash.ToLower()

# Generate manifest.json
$manifest = @{
    version = $version
    published_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
    changelog_cn = ""
    gui = @{
        installer = $guiInstaller
        sha256 = $guiHash
    }
    notification = @{
        package = $notifyExe
        sha256 = $notifyHash
    }
}
$manifest | ConvertTo-Json -Depth 3 | Set-Content -Path (Join-Path $sharedReleases "manifest.json") -Encoding UTF8

Write-Host "Pushed version $version to $sharedReleases" -ForegroundColor Green

$installerDir = Join-Path $distDir "installer"
Write-Host "=== Done ===" -ForegroundColor Green
Write-Host "App:    $distApp"
if (Test-Path $installerDir) {
    Write-Host "Setup:  $installerDir"
}

Pop-Location
