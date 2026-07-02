# Tray Update Check — Design

**Date:** 2026-07-01
**Context:** The app currently checks for updates only at startup. If the user minimizes to tray, the process keeps running indefinitely without ever re-checking. A new version deployed to the shared drive would go undetected, potentially leading to DB schema mismatches or business logic errors.

## Feature summary

When the user restores the window from the system tray (double-click or "Show Window"), run a silent update check. If a newer version exists, show a non-dismissable forced-update dialog. The user must click "Install Now" — the installer is copied, verified, and launched; the current process exits.

## Architecture

```
Tray restore (WM_LBUTTONDBLCLK / IDM_SHOW)
    │
    ▼
wnd_proc: window.show() + window.restore()
    │
    ▼
_thread_check_update_on_restore()   ← daemon thread
    │
    ├── manifest not found or same version → noop
    │
    └── new version found
          │
          ▼
        window.evaluate_js("window.__updateAvailable({...})")
          │
          ▼
        App.vue: show UpdateDialog (non-dismissable)
          │
          ▼
        User clicks "Install Now"
          │
          ▼
        callApi("install_update", {version, installer, sha256})
          │
          ▼
        bridge.install_update():
          copy installer → verify SHA256 → launch installer → os._exit(0)
```

## Backend changes

### `sc_gr_app/app_shell.py`

1. **Extract `_read_update_info()`** — a new helper that reads manifest.json and returns a dict `{version, changelog_cn, installer_name, sha256}` or `None` if no update is available or manifest is invalid/missing. Reuses existing `update.py` functions (`fetch_manifest`, `is_update_available`, `verify_manifest`). Returns `None` in dev mode or beta mode when manifest is absent.

2. **`_trigger_update_check()`** — a daemon-thread wrapper that calls `_read_update_info()`. If a dict is returned, it pushes to the JS side via `window.evaluate_js("window.__updateAvailable({...})")`. Runs after any tray restore action (both `WM_LBUTTONDBLCLK` and `IDM_SHOW`). Silently catches all exceptions — update check failure must never block window restore.

3. **Existing `_check_update()` at startup is unchanged.**

### `sc_gr_app/api/bridge.py`

4. **New bridge method `install_update(payload)`** — accepts `{version, installer, sha256}` from the frontend. Copies the installer from `releases/<installer>` to `%TEMP%/pomp-update/`, verifies SHA256, spawns `installer.exe /SILENT /DIR=<install_dir>`, then calls `os._exit(0)`. No RBAC restriction — the installer handles elevation via UAC, same as the startup update flow.

### `sc_gr_app/update.py`

No changes needed — existing `fetch_manifest`, `is_update_available`, `verify_manifest`, `sha256_file` are all reusable.

## Frontend changes

### `frontend/src/components/system/UpdateDialog.vue` (new)

A full-screen overlay dialog using Element Plus `el-dialog` with `:close-on-click-modal="false"` and no close button (`:show-close="false"`). Content:
- Title: "Update Required" (i18n)
- Body: "A new version {version} is available. You must install it to continue." + changelog text if provided
- Single button: "Install Now" with loading state

Props: `visible` (Boolean), `version` (String), `changelog` (String)
Emits: `install`

On mount, the dialog blocks all interaction — user cannot navigate away or close it.

### `frontend/src/App.vue`

- Add a `ref` for `updateInfo` (`{version, installer, sha256, changelog}` or `null`)
- Register `window.__updateAvailable = (info) => { updateInfo.value = info }` in `<script setup>` top-level
- Include `<UpdateDialog>` component, bound to `updateInfo`
- On `@install` event: calls `callApi('install_update', updateInfo)` with a try/catch showing error message on failure
- The `updateInfo` ref and `window.__updateAvailable` handler must be defined in `<script setup>` top-level (not inside `onMounted`) so the global function is registered before pywebview fires `evaluate_js`

### `frontend/src/i18n/locales/en-US.js` and `zh-CN.js`

- Add i18n keys: `update.newVersionAvailable`, `update.mustInstall`, `update.installNow`, `update.installing`

## Error handling

| Scenario | Handling |
|---|---|
| Manifest not found (dev mode) | `_read_update_info()` returns `None` — silent no-op |
| Manifest not found (beta mode) | `_read_update_info()` returns `None` — silent no-op |
| Manifest read error (production) | Logged via `logger.warning`, returns `None` — silent no-op |
| SHA256 mismatch after copy | `install_update` returns `{ok: false, error: ...}`, frontend shows error, dialog stays open |
| Installer copy failure | Same as above |
| `os._exit` failure | Theoretical — if it somehow fails, frontend shows generic error |
| Thread crashes during check | Daemon thread, silently dies — no impact on app |

## Files touched

| File | Change |
|---|---|
| `sc_gr_app/app_shell.py` | Add `_read_update_info()`, `_trigger_update_check()`; wire into tray restore paths |
| `sc_gr_app/api/bridge.py` | Add `install_update()` bridge method |
| `frontend/src/components/system/UpdateDialog.vue` | New file |
| `frontend/src/App.vue` | Register `window.__updateAvailable`, include `UpdateDialog` |
| `frontend/src/i18n/locales/en-US.js` | Add update-related i18n keys |
| `frontend/src/i18n/locales/zh-CN.js` | Add update-related i18n keys |
