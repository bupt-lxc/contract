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

# 4. Clean old build artifacts
$distDir = Join-Path (Get-Location) "dist"
$distApp = Join-Path $distDir "SC GR Management"
if (Test-Path -LiteralPath $distApp) {
    Remove-Item -LiteralPath $distApp -Recurse -Force
}
$buildDir = Join-Path (Get-Location) "build"
$buildApp = Join-Path $buildDir "app"
if (Test-Path -LiteralPath $buildApp) {
    Remove-Item -LiteralPath $buildApp -Recurse -Force
}

# 5. Generate icon from PNG (needed by PyInstaller spec files)
Write-Host "=== Generating icon ===" -ForegroundColor Cyan
$iconDir = Join-Path (Get-Location) "build\app"
if (-not (Test-Path $iconDir)) {
    New-Item -ItemType Directory -Path $iconDir -Force | Out-Null
}
uv run python -c "
from PIL import Image
img = Image.open('frontend/logo.png')
w, h = img.size
s = h
left = (w - s) // 2
img_square = img.crop((left, 0, left + s, s))
img_square.save(r'$iconDir\logo.ico', format='ICO', sizes=[(256,256),(64,64),(48,48),(32,32),(16,16)])
print('logo.ico generated')
"
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }

# 6. Build executable
Write-Host "=== Building with PyInstaller ===" -ForegroundColor Cyan
uv run pyinstaller packaging/app.spec
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }

# Read version once for Inno Setup, notification, and shared drive steps
$version = (uv run python -c "from sc_gr_app import __version__; print(__version__)").Trim()

# 7. Build Inno Setup installer
$iscc = Join-Path $env:USERPROFILE "Utils\InnoSetup6\ISCC.exe"
if (Test-Path $iscc) {
    Write-Host "=== Building installer with Inno Setup ===" -ForegroundColor Cyan
    # Sync version into setup.iss (prevents hardcoded version drift)
    $setupIss = Join-Path $PSScriptRoot "setup.iss"
    (Get-Content -Raw $setupIss) `
        -replace '#define MyAppVersion "[^"]*"', "#define MyAppVersion ""$version""" `
        -replace 'OutputBaseFilename=SC-GR-Management-[^-]*-Setup', "OutputBaseFilename=SC-GR-Management-$version-Setup" `
        | Set-Content -NoNewline $setupIss
    & $iscc $setupIss
    if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
} else {
    Write-Host "=== Skipping Inno Setup (not found) ===" -ForegroundColor Yellow
}

# 8. Build notification executable
Write-Host "=== Building notification executable ===" -ForegroundColor Cyan
uv run pyinstaller packaging/notification.spec --distpath $distDir --workpath (Join-Path $distDir "build-notification") --noconfirm
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }

# One-file mode outputs directly to dist/
$notifySrcExe = Join-Path $distDir "SC-GR-Notification.exe"
$notifyDstExe = Join-Path $distDir "SC-GR-Notification-$version.exe"
Copy-Item $notifySrcExe $notifyDstExe
Write-Host "Notification executable: $notifyDstExe" -ForegroundColor Green

# 9. Push to shared drive (only if shared drive is accessible)
$sharedReleases = Join-Path $sharedDrive "releases"
$guiInstaller = "SC-GR-Management-$version-Setup.exe"
$notifyExe = "SC-GR-Notification-$version.exe"

Write-Host "=== Pushing to shared drive ===" -ForegroundColor Cyan
if (-not (Test-Path $sharedReleases)) {
    New-Item -ItemType Directory -Path $sharedReleases -Force | Out-Null
}

# Copy files
Copy-Item -Path (Join-Path $distDir "installer\$guiInstaller") -Destination $sharedReleases -Force
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
$manifestJson = $manifest | ConvertTo-Json -Depth 3
# Use .NET UTF8Encoding($false) — no BOM — because PowerShell's Set-Content
# -Encoding UTF8 always emits a BOM, which breaks Python's json.loads().
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText((Join-Path $sharedReleases "manifest.json"), $manifestJson, $utf8NoBom)

Write-Host "Pushed version $version to $sharedReleases" -ForegroundColor Green

$installerDir = Join-Path $distDir "installer"
Write-Host "=== Done ===" -ForegroundColor Green
Write-Host "App:    $distApp"
if (Test-Path $installerDir) {
    Write-Host "Setup:  $installerDir"
}

Pop-Location
