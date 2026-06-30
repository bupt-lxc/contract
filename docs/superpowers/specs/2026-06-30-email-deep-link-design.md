# Email Deep Link — Design Spec

**Date**: 2026-06-30
**Status**: Draft

## Overview

Add deep-link buttons to all notification emails so recipients can open the corresponding entity directly in POMP. For SC/GR submit emails (manager_confirm), additionally add a "Confirm" button that navigates to the confirm UI in-app.

## Protocol

### URL Format

```
pomp://{entity_type}/{entity_id}              → Open detail page
pomp://{entity_type}/{entity_id}/confirm      → Open detail page + highlight Confirm button
```

- `entity_type`: `sc` / `po` / `gr`
- `entity_id`: entity ID string (e.g., `SC001`, `GR042`)

### Windows Registry (Inno Setup)

```ini
[Registry]
Root: HKCU; Subkey: "SOFTWARE\Classes\pomp"; ValueType: string; ValueData: "PO Management Platform Protocol"; Flags: uninsdeletekey
Root: HKCU; Subkey: "SOFTWARE\Classes\pomp"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "SOFTWARE\Classes\pomp\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""
```

HKCU (current user) because the installer uses `PrivilegesRequired=lowest`.

## Python: app_shell.py

### New functions

**`_parse_protocol_url(url)`**
Parse `pomp://sc/SC001/confirm` into `{"type": "sc", "id": "SC001", "action": "confirm"}`. Returns `None` for non-protocol URLs or parse failures.

**`_send_to_existing_window(hwnd, url)`**
Encode the URL as UTF-8 and send via `WM_COPYDATA` (0x004A) to the existing window. Exit the current process afterwards.

### Modified: `_hook_close` → rename to `_subclass_window`

Extend the existing Win32 window subclass (currently only handles `WM_CLOSE` → hide to tray) to also handle `WM_COPYDATA`:
- On receiving WM_COPYDATA, decode the URL
- Call `window.evaluate_js()` to invoke the frontend navigation handler
- Bring the window to foreground

### Modified: `_single_instance_check`

When another instance is already running AND `sys.argv[1]` contains a `pomp://` URL, call `_send_to_existing_window()` to forward the URL before exiting.

### Modified: `run_app`

After the window is shown, if `sys.argv[1]` is a `pomp://` URL, evaluate JS to trigger navigation on the first instance.

## Frontend

### app.js — Global handler

```js
window.__protocolNavigate = async function({ type, id, action }) {
  window.__pendingConfirmAction = action === 'confirm' ? { type, id } : null
  
  if (type === 'sc') {
    router.push(`/sc/${id}`)
  } else if (type === 'po') {
    router.push({ name: 'po-list', query: { highlight: id } })
  } else if (type === 'gr') {
    const gr = await callApi('get_gr', { gr_id: id })
    const po = await callApi('get_po', { po_id: gr.po_id })
    router.push(`/sc/${po.sc_id}/po/${gr.po_id}/gr/${id}`)
  }
}
```

### ScDetailView.vue / GrDetailView.vue — Highlight Confirm button

- Add `ref="confirmBtn"` on the Confirm button element
- In `onMounted`, check `window.__pendingConfirmAction`:
  - If current entity matches, scroll the button into view + add a CSS pulse animation
  - Clear `window.__pendingConfirmAction` after handling

### PoListView.vue — Highlight specific PO

- In `onMounted`, check route query param `highlight`
- If present, scroll to that PO's row in the table

## Email Templates

### templates.py: `build_body()` — add `show_confirm_btn` parameter

After the existing Detail Info table, append an "Open in POMP" button:

```html
<a href="pomp://{entity_type}/{entity_id}"
   style="display:inline-block;padding:12px 32px;
          background-color:#1a73e8;color:#fff;
          text-decoration:none;border-radius:6px;
          font-size:16px;font-weight:600">
  Open in POMP →
</a>
```

When `show_confirm_btn=True` (submit + sc/gr), also show a "Confirm" button that uses the `/confirm` variant URL.

### sender.py: `generate_draft()` / `send_entry()`

Pass `show_confirm_btn=True` when `entry["event_key"] == "submit"` and `entry["entity_type"] in ("sc", "gr")`.

## System Tray Fix

**Problem**: `_setup_tray()` silently returns if `pystray`, `PIL`, or `tray.png` are missing. In production builds, these dependencies may not be included.

**Fix**:
- `packaging/build.ps1`: add `--hidden-import=pystray --hidden-import=PIL` to PyInstaller command
- `packaging/setup.iss`: verify `tray.png` is included in the bundle
- `app_shell.py`: log a warning when tray init fails (dev debugging)

## Changed Files Summary

| File | Change |
|------|--------|
| `packaging/setup.iss` | Add `[Registry]` section for `pomp://` protocol |
| `sc_gr_app/app_shell.py` | +60 lines: protocol URL parsing, WM_COPYDATA forwarding, single-instance routing, tray warning |
| `frontend/src/app.js` | +25 lines: `__protocolNavigate()` global function |
| `frontend/src/views/ScDetailView.vue` | +10 lines: ref on confirm button, `onMounted` highlight check |
| `frontend/src/views/GrDetailView.vue` | +10 lines: same as above |
| `frontend/src/views/PoListView.vue` | +8 lines: `highlight` query param handling |
| `sc_gr_app/notification/templates.py` | +20 lines: confirm/open buttons in `build_body()` |
| `sc_gr_app/notification/sender.py` | +5 lines: pass `show_confirm_btn` to templates |
| `packaging/build.ps1` | +2 lines: PyInstaller hidden-import for pystray, PIL |
