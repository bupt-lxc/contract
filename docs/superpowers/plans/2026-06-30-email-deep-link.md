# Email Deep Link — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `pomp://` protocol deep-links to notification emails so recipients can open entities directly in POMP, with confirm-action highlight for SC/GR submit emails.

**Architecture:** Windows custom protocol (`pomp://`) registered via Inno Setup. POMP parses the URL from `sys.argv`, uses `WM_COPYDATA` for single-instance forwarding, then evaluates JS to trigger Vue Router navigation. Email templates gain persistent CTA buttons.

**Tech Stack:** Python 3.11 + ctypes (Win32), Vue 3 + Vue Router, Inno Setup

---

### Task 1: Register `pomp://` protocol in Inno Setup

**Files:**
- Modify: `packaging/setup.iss`

- [ ] **Step 1: Add `[Registry]` section**

Add after `[Files]` section:

```ini
[Registry]
Root: HKCU; Subkey: "SOFTWARE\Classes\pomp"; ValueType: string; ValueData: "PO Management Platform Protocol"; Flags: uninsdeletekey
Root: HKCU; Subkey: "SOFTWARE\Classes\pomp"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "SOFTWARE\Classes\pomp\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""
```

No test for registry entries (tested during install validation).

- [ ] **Step 2: Commit**

```bash
git add packaging/setup.iss
git commit -m "feat: register pomp:// protocol in Inno Setup installer"
```

---

### Task 2: Add CTA buttons to email templates

**Files:**
- Modify: `sc_gr_app/notification/templates.py`
- Test: `tests/test_notification_templates.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_notification_templates.py`:

```python
def test_body_includes_open_in_pomp_button_for_sc(self):
    entry = {
        "entity_type": "sc", "entity_id": "SC-001",
        "event_type": "status_change", "event_key": "approve",
    }
    entity_info = {"sc_no": "SC-001", "status": "approved", "sc_amount": 100000}
    body = templates.build_body(entry, entity_info, {})
    assert 'pomp://sc/SC-001' in body
    assert 'Open in POMP' in body

def test_body_includes_confirm_button_for_sc_submit(self):
    entry = {
        "entity_type": "sc", "entity_id": "SC-001",
        "event_type": "status_change", "event_key": "submit",
    }
    entity_info = {"sc_no": "SC-001", "status": "manager_confirm", "sc_amount": 100000}
    body = templates.build_body(entry, entity_info, {})
    assert 'pomp://sc/SC-001/confirm' in body
    assert 'Confirm' in body

def test_body_includes_confirm_button_for_gr_submit(self):
    entry = {
        "entity_type": "gr", "entity_id": "GR-001",
        "event_type": "status_change", "event_key": "submit",
    }
    entity_info = {"gr_no": "GR-001", "status": "manager_confirm", "estimated_amount": 50000}
    body = templates.build_body(entry, entity_info, {})
    assert 'pomp://gr/GR-001/confirm' in body
    assert 'Confirm' in body

def test_body_no_confirm_button_for_non_submit(self):
    entry = {
        "entity_type": "sc", "entity_id": "SC-001",
        "event_type": "status_change", "event_key": "approve",
    }
    entity_info = {"sc_no": "SC-001", "status": "approved", "sc_amount": 100000}
    body = templates.build_body(entry, entity_info, {})
    assert 'pomp://sc/SC-001/confirm' not in body

def test_open_in_pomp_button_for_po(self):
    entry = {
        "entity_type": "po", "entity_id": "PO-001",
        "event_type": "status_change", "event_key": "finish",
    }
    entity_info = {"po_no": "PO-001", "status": "finished", "po_amount": 80000}
    body = templates.build_body(entry, entity_info, {})
    assert 'pomp://po/PO-001' in body
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_notification_templates.py::test_body_includes_open_in_pomp_button_for_sc -q
```
Expected: FAIL (no pomp:// URL in body)

- [ ] **Step 3: Add button HTML to `build_body()`**

Modify `build_body()` signature to accept `show_confirm_btn: bool = False`:

```python
def build_body(entry: dict, entity_info: dict, user_emails: dict,
               actor_name: str = "", requester_name: str = "",
               show_confirm_btn: bool = False) -> str:
```

Append button row after the existing tables (before `return "\n".join(lines)`):

```python
    # ── CTA buttons ──────────────────────────────────────────────────
    entity_type = entry["entity_type"]
    entity_id = entry["entity_id"]

    lines.append(
        '<table style="width:100%;border-collapse:collapse;'
        'font-family:Arial,sans-serif;font-size:14px;margin-top:24px">'
        '<tr><td align="center" style="padding:4px">'
    )

    # Always show "Open in POMP" button
    open_url = f"pomp://{entity_type}/{entity_id}"
    lines.append(
        f'<a href="{open_url}" '
        f'style="display:inline-block;padding:12px 32px;'
        f'background-color:#1a73e8;color:#fff;'
        f'text-decoration:none;border-radius:6px;'
        f'font-size:16px;font-weight:600">'
        f'Open in POMP →</a>'
    )

    # Additional "Confirm" button for SC/GR submit events
    if show_confirm_btn:
        confirm_url = f"pomp://{entity_type}/{entity_id}/confirm"
        lines.append('&nbsp;&nbsp;')
        lines.append(
            f'<a href="{confirm_url}" '
            f'style="display:inline-block;padding:12px 32px;'
            f'background-color:#34a853;color:#fff;'
            f'text-decoration:none;border-radius:6px;'
            f'font-size:16px;font-weight:600">'
            f'Confirm this {entity_type.upper()} →</a>'
        )

    lines.append(
        '<p style="margin-top:12px;font-size:12px;color:#9aa0a6">'
        'Clicking this button will open PO Management Platform.'
        ' If the app is not running, please start POMP first.</p>'
        '</td></tr></table>'
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_notification_templates.py -q -k "pomp"
```
Expected: all 5 new tests PASS

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/notification/templates.py tests/test_notification_templates.py
git commit -m "feat: add Open in POMP and Confirm buttons to notification email body"
```

---

### Task 3: Pass `show_confirm_btn` flag from sender

**Files:**
- Modify: `sc_gr_app/notification/sender.py`

- [ ] **Step 1: Add flag logic in `generate_draft()`**

In `generate_draft()`, replace the `build_body()` call (line 277) with:

```python
    show_confirm = (
        entry["event_key"] == "submit"
        and entry["entity_type"] in ("sc", "gr")
    )
    body = templates.build_body(entry, entity_info, {**to_emails_map, **cc_emails_map},
                                actor_name=actor_name, requester_name=requester_name,
                                show_confirm_btn=show_confirm)
```

- [ ] **Step 2: Add flag logic in `send_entry()`**

In `send_entry()`, replace the `build_body()` call (line 354) with:

```python
        show_confirm = (
            entry["event_key"] == "submit"
            and entry["entity_type"] in ("sc", "gr")
        )
        body = templates.build_body(entry, entity_info, {**to_emails_map, **cc_emails_map},
                                    actor_name=actor_name, requester_name=requester_name,
                                    show_confirm_btn=show_confirm)
```

- [ ] **Step 3: Run existing tests to check no regressions**

```bash
uv run pytest tests/test_notification_templates.py -q
```
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/notification/sender.py
git commit -m "feat: pass show_confirm_btn flag to email template from sender"
```

---

### Task 4: Protocol URL parsing and WM_COPYDATA in app_shell.py

**Files:**
- Modify: `sc_gr_app/app_shell.py`

- [ ] **Step 1: Add ctypes setup for SendMessageW and COPYDATASTRUCT**

After the existing `_kernel32.CreateMutexW` argtypes (line 80), add:

```python
WM_COPYDATA = 0x004A

class COPYDATASTRUCT(ctypes.Structure):
    _fields_ = [
        ("dwData", ctypes.c_ulonglong),
        ("cbData", ctypes.c_uint),
        ("lpData", ctypes.c_void_p),
    ]

_user32.SendMessageW.restype = ctypes.c_longlong
_user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_ulonglong, ctypes.c_longlong]
```

- [ ] **Step 2: Insert `_parse_protocol_url()` and `_send_to_existing_window()` before `_single_instance_check()`**

Insert after the `_kernel32` argtypes block (before `def _patch_webview2()`):

```python
def _parse_protocol_url(url: str) -> dict | None:
    """Parse pomp://sc/SC001/confirm into {type, id, action}. Returns None on failure."""
    if not url or not url.startswith("pomp://"):
        return None
    path = url[len("pomp://"):].rstrip("/")
    parts = path.split("/")
    if len(parts) < 2:
        return None
    entity_type = parts[0]
    if entity_type not in ("sc", "po", "gr"):
        return None
    result = {"type": entity_type, "id": parts[1], "action": None}
    if len(parts) >= 3 and parts[2] == "confirm":
        result["action"] = "confirm"
    return result


def _send_to_existing_window(hwnd, url: str) -> None:
    """Forward a pomp:// URL to an already-running POMP window via WM_COPYDATA."""
    encoded = url.encode("utf-8")
    cds = COPYDATASTRUCT()
    cds.dwData = 0
    cds.cbData = len(encoded)
    buf = ctypes.create_string_buffer(encoded)
    cds.lpData = ctypes.cast(buf, ctypes.c_void_p)
    _user32.SendMessageW(hwnd, WM_COPYDATA, 0, ctypes.c_void_p(ctypes.addressof(cds)))
    # Bring the existing window to foreground
    _user32.ShowWindow(hwnd, 5)    # SW_SHOW
    _user32.ShowWindow(hwnd, 9)    # SW_RESTORE
    _user32.SetForegroundWindow(hwnd)
```

- [ ] **Step 3: Modify `_single_instance_check()` to forward protocol URL**

Replace the existing `_single_instance_check()` with:

```python
def _single_instance_check():
    mutex = _kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if _kernel32.GetLastError() != 183:
        return
    hwnd = _user32.FindWindowW(None, WINDOW_TITLE)
    if hwnd:
        # If launched with a pomp:// URL, forward it to the existing window
        if len(sys.argv) > 1 and _parse_protocol_url(sys.argv[1]):
            _send_to_existing_window(hwnd, sys.argv[1])
        else:
            _user32.ShowWindow(hwnd, 5)    # SW_SHOW
            _user32.ShowWindow(hwnd, 9)    # SW_RESTORE
            _user32.SetForegroundWindow(hwnd)
    sys.exit(0)
```

- [ ] **Step 4: Extend `_subclass_window()` to handle WM_COPYDATA**

Inside `_subclass_window(hwnd)`, add after the `WM_CLOSE` handler block and before the `WM_TRAYICON` handler block:

```python
            # ── WM_COPYDATA: protocol URL from secondary instance ────
            if msg == WM_COPYDATA:
                cds = ctypes.cast(ctypes.c_void_p(lparam), ctypes.POINTER(COPYDATASTRUCT)).contents
                url_bytes = ctypes.cast(cds.lpData, ctypes.c_char_p).value.decode("utf-8")
                window.show()
                window.restore()
                window.evaluate_js(
                    f"window.__protocolNavigate({url_bytes})"
                )
                return 0
```

- [ ] **Step 5: Modify `run_app()` to handle protocol URL on first launch**

After the `_setup_tray(window)` line, add:

```python
    # Check for pomp:// protocol URL on first launch
    protocol_params = None
    if len(sys.argv) > 1:
        protocol_params = _parse_protocol_url(sys.argv[1])

    def _on_loaded():
        if protocol_params:
            import json
            js = json.dumps(protocol_params)
            window.evaluate_js(f"window.__protocolNavigate({js})")

    window.events.loaded += _on_loaded
```

- [ ] **Step 6: Commit**

```bash
git add sc_gr_app/app_shell.py
git commit -m "feat: parse pomp:// protocol URL and forward via WM_COPYDATA for single-instance support"
```

---

### Task 5: Frontend `__protocolNavigate` global handler

**Files:**
- Modify: `frontend/src/main.js`

- [ ] **Step 1: Add `__protocolNavigate` before `app.mount()`**

In `main.js`, add after `app.use(i18n)` and before `app.mount('#app')`:

```js
import { callApi } from '@/api/bridge.js'

window.__protocolNavigate = async function(params) {
  // params is { type: 'sc'|'po'|'gr', id: string, action: 'confirm'|null }
  window.__pendingConfirmAction = params.action === 'confirm'
    ? { type: params.type, id: params.id }
    : null

  if (params.type === 'sc') {
    router.push(`/sc/${params.id}`)
  } else if (params.type === 'po') {
    const po = await callApi('get_po', { po_id: params.id })
    router.push(`/sc/${po.sc_id}/po/${params.id}`)
  } else if (params.type === 'gr') {
    const gr = await callApi('get_gr', { gr_id: params.id })
    const po = await callApi('get_po', { po_id: gr.po_id })
    router.push(`/sc/${po.sc_id}/po/${gr.po_id}/gr/${params.id}`)
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/main.js
git commit -m "feat: add __protocolNavigate global handler for pomp:// deep links"
```

---

### Task 6: Highlight Confirm button in ScDetailView

**Files:**
- Modify: `frontend/src/views/ScDetailView.vue`

- [ ] **Step 1: Add `ref="confirmBtn"` on the Confirm button**

In the template, change line 14:

```html
<el-button v-if="permissions.can_confirm_sc" ref="confirmBtn" type="primary" :disabled="loadingState.count > 0" @click="handleConfirm">{{ $t('sc.confirm') }}</el-button>
```

- [ ] **Step 2: Add highlight logic in `onMounted`**

In the `<script setup>` section, add a `confirmBtn` ref:

```js
const confirmBtn = ref(null)
```

At the end of the existing `onMounted` callback (line 421), add:

```js
  if (window.__pendingConfirmAction?.type === 'sc' && window.__pendingConfirmAction?.id === scId.value) {
    window.__pendingConfirmAction = null
    setTimeout(() => {
      confirmBtn.value?.$el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      confirmBtn.value?.$el?.classList.add('confirm-pulse')
      setTimeout(() => confirmBtn.value?.$el?.classList.remove('confirm-pulse'), 3000)
    }, 500)
  }
```

- [ ] **Step 3: Add CSS pulse animation**

In the `<style scoped>` section (or global if used across views), add:

```css
.confirm-pulse {
  animation: pulse 0.6s ease-in-out 3;
  box-shadow: 0 0 0 0 rgba(52, 168, 83, 0.6);
}
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(52, 168, 83, 0.6); }
  50% { box-shadow: 0 0 0 8px rgba(52, 168, 83, 0); }
  100% { box-shadow: 0 0 0 0 rgba(52, 168, 83, 0); }
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/ScDetailView.vue
git commit -m "feat: highlight Confirm button when SC opened via pomp:// confirm deep link"
```

---

### Task 7: Highlight Confirm button in GrDetailView

**Files:**
- Modify: `frontend/src/views/GrDetailView.vue`

- [ ] **Step 1: Add `ref="confirmBtn"` on the Confirm button**

In the template (line 10), change:

```html
<el-button v-if="scDetail?.permissions?.is_admin && gr.status === 'manager_confirm'" ref="confirmBtn" type="primary" :disabled="loadingState.count > 0" @click="handleConfirm">{{ $t('gr.confirm') }}</el-button>
```

- [ ] **Step 2: Add highlight logic and ref**

In `<script setup>`, add:

```js
const confirmBtn = ref(null)
```

In the `onMounted` callback, add:

```js
  if (window.__pendingConfirmAction?.type === 'gr' && window.__pendingConfirmAction?.id === grId.value) {
    window.__pendingConfirmAction = null
    setTimeout(() => {
      confirmBtn.value?.$el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      confirmBtn.value?.$el?.classList.add('confirm-pulse')
      setTimeout(() => confirmBtn.value?.$el?.classList.remove('confirm-pulse'), 3000)
    }, 500)
  }
```

- [ ] **Step 3: Add CSS pulse animation** (same as ScDetailView)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/GrDetailView.vue
git commit -m "feat: highlight Confirm button when GR opened via pomp:// confirm deep link"
```

---

### Task 8: End-to-end verification

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest -q
```
Expected: all tests PASS

- [ ] **Step 2: Verify frontend builds**

```bash
cd frontend && npm run build
```
Expected: build succeeds with no errors

- [ ] **Step 3: Manual smoke test checklist**

1. Build and install POMP via the installer
2. Verify `pomp://` is registered: open browser, navigate to `pomp://sc/xxx` → POMP should launch
3. Verify single-instance: POMP running → click `pomp://sc/yyy` in browser → existing window navigates
4. Send a test notification email → verify "Open in POMP" button appears in the HTML
5. Submit an SC → verify the resulting email has both "Open in POMP" and "Confirm" buttons
6. Click the "Confirm" button → POMP opens SC detail → Confirm button pulses
```
