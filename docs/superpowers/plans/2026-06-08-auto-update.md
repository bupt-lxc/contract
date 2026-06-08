# Auto-Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automatic update capability for GUI and notification components, pulling new versions from the shared drive.

**Architecture:** New `update.py` shared module provides pure read-only functions used by both GUI (`app_shell.py`) and notification (`__main__.py`). GUI checks on startup before DB init, mandatory update. Notification checks before each `--run-once` cycle, auto-silent with failure fallback. Both skip in dev mode (`SC_GR_DEV=1`).

**Tech Stack:** Python 3.11, sqlite3, ctypes (MessageBoxW), hashlib (SHA256), PowerShell (build script)

---

### Task 1: `sc_gr_app/update.py` — shared update module

**Files:**
- Create: `sc_gr_app/update.py`
- Create: `tests/test_update.py`

- [ ] **Step 1: Write the test file**

```python
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from sc_gr_app import __version__
from sc_gr_app.config import AppConfig
from sc_gr_app.update import (
    fetch_manifest,
    verify_manifest,
    is_update_available,
    sha256_file,
)


def make_config(tmp_path: Path) -> AppConfig:
    """Create an AppConfig with db_path at tmp_path/data/sc_gr.sqlite3."""
    return AppConfig(
        db_path=tmp_path / "data" / "sc_gr.sqlite3",
        lock_dir=tmp_path / "data" / "locks",
    )


class TestFetchManifest:
    def test_returns_none_in_dev_mode(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SC_GR_DEV", "1")
        config = make_config(tmp_path)
        assert fetch_manifest(config) is None

    def test_returns_none_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SC_GR_DEV", raising=False)
        config = make_config(tmp_path)
        assert fetch_manifest(config) is None

    def test_returns_dict_when_manifest_exists(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SC_GR_DEV", raising=False)
        config = make_config(tmp_path)
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir(parents=True)
        manifest = {
            "version": "2.0.0",
            "published_at": "2026-06-08T15:30:00Z",
            "changelog_cn": "测试",
            "gui": {"installer": "test-setup.exe", "sha256": "abc"},
            "notification": {"package": "test-notify.exe", "sha256": "def"},
        }
        (releases_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        result = fetch_manifest(config)
        assert result == manifest

    def test_returns_none_on_parse_error(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SC_GR_DEV", raising=False)
        config = make_config(tmp_path)
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir(parents=True)
        (releases_dir / "manifest.json").write_text("not json", encoding="utf-8")
        assert fetch_manifest(config) is None


class TestVerifyManifest:
    def test_valid_manifest(self):
        manifest = {
            "version": "2.0.0",
            "gui": {"installer": "test-setup.exe", "sha256": "abc"},
            "notification": {"package": "test-notify.exe", "sha256": "def"},
        }
        assert verify_manifest(manifest) is True

    def test_none_is_false(self):
        assert verify_manifest(None) is False

    def test_missing_gui_installer(self):
        manifest = {
            "version": "2.0.0",
            "gui": {"sha256": "abc"},
            "notification": {"package": "test.exe", "sha256": "def"},
        }
        assert verify_manifest(manifest) is False

    def test_missing_notification_package(self):
        manifest = {
            "version": "2.0.0",
            "gui": {"installer": "test-setup.exe", "sha256": "abc"},
            "notification": {"sha256": "def"},
        }
        assert verify_manifest(manifest) is False

    def test_missing_version(self):
        manifest = {
            "gui": {"installer": "test-setup.exe", "sha256": "abc"},
            "notification": {"package": "test.exe", "sha256": "def"},
        }
        assert verify_manifest(manifest) is False

    def test_version_not_string(self):
        manifest = {
            "version": 3,
            "gui": {"installer": "test-setup.exe", "sha256": "abc"},
            "notification": {"package": "test.exe", "sha256": "def"},
        }
        assert verify_manifest(manifest) is False


class TestIsUpdateAvailable:
    def test_different_version(self):
        manifest = {"version": "99.99.99"}
        other = __version__ != "99.99.99"
        assert is_update_available(manifest) is other

    def test_same_version(self):
        manifest = {"version": __version__}
        assert is_update_available(manifest) is False

    def test_none(self):
        assert is_update_available(None) is False

    def test_no_version_key(self):
        assert is_update_available({}) is False


class TestSha256File:
    def test_known_content(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello")
        digest = sha256_file(f)
        assert digest == hashlib.sha256(b"hello").hexdigest()

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        digest = sha256_file(f)
        assert digest == hashlib.sha256(b"").hexdigest()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_update.py -q`
Expected: FAIL — ModuleNotFoundError for sc_gr_app.update

- [ ] **Step 3: Write the module**

```python
import hashlib
import json
import os
from pathlib import Path

from sc_gr_app import __version__
from sc_gr_app.config import AppConfig

REQUIRED_MANIFEST_PATHS = [
    ("version",),
    ("gui", "installer"),
    ("gui", "sha256"),
    ("notification", "package"),
    ("notification", "sha256"),
]


def fetch_manifest(config: AppConfig) -> dict | None:
    if os.getenv("SC_GR_DEV") == "1":
        return None
    manifest_path = config.db_path.parent.parent / "releases" / "manifest.json"
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def verify_manifest(manifest: dict) -> bool:
    if manifest is None:
        return False
    try:
        for path in REQUIRED_MANIFEST_PATHS:
            node = manifest
            for key in path:
                node = node[key]
        return isinstance(manifest.get("version"), str)
    except (KeyError, TypeError):
        return False


def is_update_available(manifest: dict) -> bool:
    if manifest is None:
        return False
    current = manifest.get("version")
    return isinstance(current, str) and current != __version__


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_update.py -v`
Expected: all 13 tests PASS

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/update.py tests/test_update.py
git commit -m "feat: add shared update module for auto-update checks"
```

---

### Task 2: `sc_gr_app/app_shell.py` — implement `_check_update` for GUI

**Files:**
- Modify: `sc_gr_app/app_shell.py:94-96` (replace placeholder `_check_update`)
- Modify: `sc_gr_app/app_shell.py:194` (call `_check_update` before `_init_database`)

- [ ] **Step 1: Replace the placeholder `_check_update` function (lines 94-96)**

```python
def _check_update():
    """Check for and apply updates from shared drive. Called before _init_database.
    Exits the process if an update is found and launched, or on fatal errors."""
    from sc_gr_app.update import fetch_manifest, is_update_available, verify_manifest, sha256_file

    manifest = fetch_manifest(default_config())
    if manifest is None:
        if os.getenv("SC_GR_DEV") == "1":
            return
        _show_error_and_exit(
            "SC GR Management — Update Error",
            "Unable to check for updates.\n\nVerify the shared drive is accessible.",
        )

    if not is_update_available(manifest):
        return

    if not verify_manifest(manifest):
        _show_error_and_exit(
            "SC GR Management — Update Error",
            "Update manifest is invalid. Contact your administrator.",
        )

    new_version = manifest["version"]
    changelog = manifest.get("changelog_cn", "")
    body = f"Found version {new_version}\n\n{changelog}\n\nClick OK to install the update."
    rc = _user32.MessageBoxW(0, body, "SC GR Management — Update Available", 0x40 | 0x01)  # MB_ICONINFORMATION | MB_OKCANCEL
    if rc != 1:  # IDOK
        sys.exit(0)

    installer_name = manifest["gui"]["installer"]
    expected_hash = manifest["gui"]["sha256"]
    releases_dir = default_config().db_path.parent.parent / "releases"
    installer_src = releases_dir / installer_name
    temp_dir = Path(os.getenv("TEMP")) / "sc-gr-update"
    temp_dir.mkdir(parents=True, exist_ok=True)
    installer_dst = temp_dir / installer_name

    try:
        import shutil
        shutil.copy2(installer_src, installer_dst)
    except OSError:
        _show_error_and_exit(
            "SC GR Management — Update Error",
            "Failed to copy the update. Verify the shared drive is accessible.",
        )

    actual_hash = sha256_file(installer_dst)
    if actual_hash != expected_hash:
        _show_error_and_exit(
            "SC GR Management — Update Error",
            "Update file is corrupted. Contact your administrator.",
        )

    install_dir = Path(sys.executable).parent
    try:
        import subprocess
        subprocess.Popen(
            [
                str(installer_dst),
                "/VERYSILENT",
                f"/DIR={install_dir}",
            ],
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except OSError:
        _show_error_and_exit(
            "SC GR Management — Update Error",
            "Failed to start the installer. Contact your administrator.",
        )

    sys.exit(0)
```

- [ ] **Step 2: Update `run_app` to call `_check_update` before `_init_database`**

Replace lines 194-224 of `run_app` — the current ordering:

```python
def run_app():
    _single_instance_check()
    _patch_webview2()

    _check_update()  # <-- inserted here, before DB init

    config, init_error = _init_database()
    ...
```

The exact edit: insert `_check_update()` between `_patch_webview2()` and the `config, init_error = _init_database()` line.

- [ ] **Step 3: Verify existing imports are sufficient**

The `_check_update` function uses `default_config` (already imported from `sc_gr_app.config`), `os`, and `sys` (already imported at top of `app_shell.py`). `Path` is already imported. `_user32` and `_show_error_and_exit` are already defined. No new top-level imports needed.

- [ ] **Step 4: Run the app in dev mode to confirm update check is skipped**

Run: `uv run python -m sc_gr_app.main` (with `SC_GR_DEV=1`)
Expected: app starts normally, no update prompt

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/app_shell.py
git commit -m "feat: implement mandatory update check in GUI startup"
```

---

### Task 3: `sc_gr_app/notification/__main__.py` — insert update check for notification

**Files:**
- Modify: `sc_gr_app/notification/__main__.py:39-53` (insert update check in `--run-once` and `--thresholds-only` paths)

- [ ] **Step 1: Add notification update logic in `main()`**

Replace the entire `main()` function in `sc_gr_app/notification/__main__.py`:

```python
def main():
    parser = argparse.ArgumentParser(description="Email notification script")
    parser.add_argument("--poll-interval", type=int, default=300,
                        help="Seconds between queue checks (default: 300)")
    parser.add_argument("--run-once", action="store_true",
                        help="Run one cycle and exit")
    parser.add_argument("--thresholds-only", action="store_true",
                        help="Run only the threshold check and exit")
    parser.add_argument("--draft", action="store_true",
                        help="Save emails to Drafts folder instead of sending (dev mode)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    if args.draft:
        sender.set_draft_mode(True)

    config = default_config()
    logging.info("Using database: %s", config.db_path)

    # Update check for run-once and thresholds-only modes
    if args.run_once or args.thresholds_only:
        _check_for_update(config)

    if args.thresholds_only:
        engine.run_thresholds_only(config)
    elif args.run_once:
        engine.run_once(config)
    else:
        engine.run_poll_loop(config, poll_interval=args.poll_interval)


def _check_for_update(config):
    """Check for notification update. On success, replaces current exe and exits.
    On any failure, logs and returns silently (email delivery takes priority)."""
    import os
    import shutil
    import sys
    from pathlib import Path

    from sc_gr_app.update import fetch_manifest, is_update_available, verify_manifest, sha256_file

    manifest = fetch_manifest(config)
    if manifest is None or not is_update_available(manifest):
        return

    if not verify_manifest(manifest):
        logging.warning("Update manifest invalid, skipping update")
        return

    new_version = manifest["version"]
    package_name = manifest["notification"]["package"]
    expected_hash = manifest["notification"]["sha256"]
    releases_dir = config.db_path.parent.parent / "releases"
    package_src = releases_dir / package_name
    temp_dir = Path(os.getenv("TEMP")) / "sc-gr-update"
    temp_dir.mkdir(parents=True, exist_ok=True)
    package_dst = temp_dir / package_name

    try:
        shutil.copy2(package_src, package_dst)
    except OSError:
        logging.warning("Failed to copy notification update from shared drive, skipping")
        return

    actual_hash = sha256_file(package_dst)
    if actual_hash != expected_hash:
        logging.warning("Notification update SHA256 mismatch, skipping")
        return

    current_exe = Path(sys.executable)
    old_exe = current_exe.with_suffix(".exe.old")

    try:
        if old_exe.exists():
            old_exe.unlink()
        current_exe.rename(old_exe)
        shutil.copy2(package_dst, current_exe)
    except OSError:
        logging.warning("Failed to replace notification exe, skipping")
        return

    # Schedule old file deletion on next reboot
    import ctypes
    try:
        ctypes.windll.kernel32.MoveFileExW(str(old_exe), None, 4)  # MOVEFILE_DELAY_UNTIL_REBOOT = 4
    except Exception:
        pass

    logging.info("Notification updated to v%s, exiting for restart by scheduler", new_version)
    sys.exit(0)
```

- [ ] **Step 2: Run notification in dev mode to confirm update check is skipped**

Run: `uv run python -m sc_gr_app.notification --run-once --draft` (with `SC_GR_DEV=1`)
Expected: runs email send cycle normally, no update-related output

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/notification/__main__.py
git commit -m "feat: add auto-update check to notification run-once mode"
```

---

### Task 4: `packaging/notification.spec` — PyInstaller spec for notification process

**Files:**
- Create: `packaging/notification.spec`

- [ ] **Step 1: Write the spec file**

```python
from pathlib import Path

project_root = Path(SPECPATH).parent

a = Analysis(
    [str(project_root / "sc_gr_app" / "notification" / "__main__.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(project_root / "sc_gr_app" / "db" / "schema.sql"), "sc_gr_app/db"),
    ],
    hiddenimports=[
        "win32com",
        "win32com.client",
        "pythoncom",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SC-GR-Notification",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,           # console mode — stdout visible for logging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SC-GR-Notification",
)
```

- [ ] **Step 2: Verify the spec file is valid Python syntax**

Run: `uv run python -c "compile(open('packaging/notification.spec').read(), 'notification.spec', 'exec'); print('OK')"`
Expected: prints `OK`

- [ ] **Step 3: Commit**

```bash
git add packaging/notification.spec
git commit -m "build: add PyInstaller spec for notification process"
```

---

### Task 5: `packaging/build.ps1` — add notification build + push stage

**Files:**
- Modify: `packaging/build.ps1`

- [ ] **Step 1: Add notification build step after Inno Setup (before "Done")**

Insert after the Inno Setup section (after `Write-Host "=== Skipping Inno Setup ==="`) and before the final `Write-Host "=== Done ==="` lines:

```powershell
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
```

- [ ] **Step 2: Add push stage after all builds pass**

Insert after the notification build step:

```powershell
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
```

- [ ] **Step 3: Define `$sharedDrive` variable at top of build.ps1**

After the `Push-Location` line, add:

```powershell
$sharedDrive = "\\ap.vwg\fileshare\AUDI CHINA\Audi_China_RnD\R&D\EG\10_EG-V\80000_EG_W\DMAS\01 Daily working files\contract"
Write-Host "Shared drive: $sharedDrive" -ForegroundColor Cyan
```

- [ ] **Step 4: Commit**

```bash
git add packaging/build.ps1
git commit -m "build: add notification build and shared-drive push stage"
```

---

### Task 6: End-to-end verification

**Files:**
- No changes — verification only

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -q`
Expected: all existing tests + new update tests PASS

- [ ] **Step 2: Verify update.py module integration**

Run: `uv run python -c "from sc_gr_app.update import fetch_manifest, verify_manifest, is_update_available, sha256_file; print('OK')"`
Expected: prints `OK`

- [ ] **Step 3: Verify notification update import works standalone**

Run: `uv run python -c "from sc_gr_app.notification.__main__ import _check_for_update; print('OK')"`
Expected: prints `OK`

- [ ] **Step 4: Verify build script syntax (PowerShell parse check)**

Run: `powershell -Command "Get-Command packaging/build.ps1 -Syntax"`
Expected: shows syntax without errors

- [ ] **Step 5: Commit**

```bash
git add -A
git diff --cached --stat
git commit -m "chore: final verification after auto-update implementation"
```
