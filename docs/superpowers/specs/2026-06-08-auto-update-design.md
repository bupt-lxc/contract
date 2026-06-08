# Auto-Update Design

## Overview

Add automatic update capability for both the GUI desktop app and the notification (mail sender) process. The shared drive (`\\ap.vwg\...\contract\`) is the single distribution source — no external server needed.

**Key decisions:**
- GUI: mandatory update on startup, before auth. Failure → exit.
- Notification: auto-silent update before sending. Failure → skip, send with old version.
- Dev mode (`SC_GR_DEV=1`): skips all update logic.
- Unified version number for both components.
- Notification runs via Windows Scheduled Task (`--run-once` per minute).
- Build script auto-pushes artifacts to shared drive after tests pass.

## Artifacts

| File | Action |
|---|---|
| `sc_gr_app/update.py` | New: shared update module |
| `sc_gr_app/app_shell.py` | Modify: implement `_check_update` |
| `sc_gr_app/notification/__main__.py` | Modify: insert update check in `--run-once` |
| `packaging/notification.spec` | New: PyInstaller spec for notification process |
| `packaging/build.ps1` | Modify: add notification build + push stage |

## Shared Drive Layout

```
\\ap.vwg\...\contract\
  data/                          (existing: database, locks)
  releases/                      (new)
    manifest.json
    SC-GR-Management-{version}-Setup.exe
    SC-GR-Notification-{version}.exe
```

`releases/` is a sibling directory to `data/`, derived from `config.db_path.parent.parent / "releases"`.

## manifest.json

```json
{
  "version": "2.1.0",
  "published_at": "2026-06-08T15:30:00Z",
  "changelog_cn": "...",
  "gui": {
    "installer": "SC-GR-Management-2.1.0-Setup.exe",
    "sha256": "e3b0c44..."
  },
  "notification": {
    "package": "SC-GR-Notification-2.1.0.exe",
    "sha256": "a1b2c3d..."
  }
}
```

- `version` is the single source of truth; both components share it.
- File names include version for human readability when browsing the releases directory.
- `changelog_cn` shown in GUI update prompt.

## Build & Push (build.ps1)

```
Vue build → uv sync → tests
  ├─ PyInstaller (packaging/app.spec)       → dist/SC GR Management/
  │   └─ Inno Setup                         → dist/installer/SC-GR-Management-{version}-Setup.exe
  ├─ PyInstaller (packaging/notification.spec) → dist/SC-GR-Notification-{version}.exe
  │
  └─ Push stage (only if tests pass):
      1. Compute SHA256 for both files
      2. Generate manifest.json
      3. Copy installer + notification.exe + manifest to shared drive releases/
      4. Overwrite manifest; old installers remain (for potential rollback)
```

`packaging/notification.spec` builds a single console-mode executable (no GUI window, stdout visible).

## Shared Module: `sc_gr_app/update.py`

Three public functions used by both GUI and notification:

```python
def fetch_manifest(config: AppConfig) -> dict | None
def verify_manifest(manifest: dict) -> bool
def is_update_available(manifest: dict) -> bool
```

- `fetch_manifest`: derives releases path from `config.db_path.parent.parent / "releases" / "manifest.json"` (releases is sibling to `data/`). Returns `None` on failure or if `SC_GR_DEV=1`.
- `verify_manifest`: validates manifest structure and required fields (`version`, `gui.installer`, `gui.sha256`, `notification.package`, `notification.sha256`). No cryptographic signature (shared drive is the trust boundary). Returns `bool`.
- `is_update_available`: `manifest["version"] != __version__`.

Module is side-effect-free (read only).

## GUI Flow

```
_single_instance_check
    ↓
SC_GR_DEV=1? ── yes ──→ skip update, continue normal startup
    ↓ no
fetch_manifest ── fail ──→ MessageBoxW error → exit(1)
    ↓ ok
is_update_available? ── no ──→ continue normal startup
    ↓ yes
verify_manifest ── fail ──→ MessageBoxW error → exit(1)
    ↓ ok
MessageBoxW: "Found v{version}\n{changelog_cn}" [Update]
    ↓
Copy installer to %TEMP%\sc-gr-update\
    ↓
Verify installer SHA256 ── fail ──→ MessageBoxW error → exit(1)
    ↓ ok
Launch installer with:
  - /VERYSILENT: no UI, no progress bar
  - /DIR="{current_install_dir}": install to same location
    ↓
Current process exit(0)
    ↓
Inno Setup overwrites files → auto-restarts new version
```

Design notes:
- Update check runs after `_single_instance_check` but BEFORE `_init_database` — no point reaching the DB if we're about to exit for an update.
- `MessageBoxW` (already used in app_shell.py) for the prompt — webview is not created yet.
- Only one button: "Update". No cancel, no skip.
- SHA256 mismatch means file corruption on shared drive → exit, user reports to admin.

## Notification Flow

Entry point: Windows Scheduled Task triggers `SC-GR-Notification.exe --run-once` every minute.

```
Scheduled Task trigger
    ↓
_default_config → connect
    ↓
SC_GR_DEV=1? ── yes ──→ skip update, continue to send
    ↓ no
fetch_manifest ── fail ──→ log warning, continue to send
    ↓ ok
is_update_available? ── no ──→ continue to send
    ↓ yes
verify_manifest ── fail ──→ log warning, continue to send
    ↓ ok
Copy new notification.exe from shared drive to %TEMP%
    ↓
Verify SHA256 ── fail ──→ log warning, continue to send
    ↓ ok
Rename current exe → "SC-GR-Notification.exe.old"
Copy new exe from %TEMP% to original location → "SC-GR-Notification.exe"
Schedule old file deletion: MoveFileEx(".old", NULL, MOVEFILE_DELAY_UNTIL_REBOOT)
    ↓
Skip current batch. Log info. exit(0)
    ↓
Next Scheduled Task trigger → runs new exe
```

Design notes:
- Unlike GUI, shared drive failures never exit — email delivery takes priority.
- Update failure → log and continue sending with old version.
- On success, skip current batch to avoid mid-replacement issues.
- No restart needed: Scheduled Task fires again next minute with the new exe.
- Replace strategy: rename current exe to .old (running exe can be renamed, not overwritten), copy new exe to original name, schedule .old for delete on next reboot.

## How GUI finds its install directory

The GUI needs to know where the installer should install (the `/DIR` parameter). Use `sys.executable` at runtime to locate the current exe, then derive the install directory as its parent. In production this will be e.g. `C:\Program Files\SC GR Management`.

## Dev Mode

When `SC_GR_DEV=1`:
- `fetch_manifest` returns `None` immediately — no manifest read, no shared drive access.
- Both GUI and notification skip all update logic transparently.
- `dev.ps1` already sets this env var for both processes.
