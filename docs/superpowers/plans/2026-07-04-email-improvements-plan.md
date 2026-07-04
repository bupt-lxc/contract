# Email Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add greeting lines to operational emails, make sender email configurable via system settings, and fix OpenConsole residual process.

**Architecture:** Three independent changes. Task 1 adds a greeting paragraph in `templates.py:build_body()` before the Notification Info table. Task 2 adds a sender email input in SystemView.vue, two bridge APIs (`get_sender_email`/`set_sender_email`), and `SendUsingAccount` logic in `sender.py`. Task 3 flips `console=False` in the PyInstaller spec.

**Tech Stack:** Python (win32com, sqlite3), Vue 3 (Element Plus), PyInstaller

---

### Task 1: Add greeting line to operational email body

**Files:**
- Modify: `sc_gr_app/notification/templates.py` — `build_body()` function (around line 380)
- Modify: `tests/test_notification_templates.py` — add greeting assertion to existing tests

- [ ] **Step 1: Add greeting line in `build_body()`**

In `sc_gr_app/notification/templates.py`, inside `build_body()`, insert a greeting paragraph after the variable declarations and before the "Table 1: Notification Info" comment (around line 380).

Find this block:
```python
    # Table 1: Notification Info
    lines = []
    lines.append('<table style="width:100%;border-collapse:collapse;font-family:Arial,sans-serif;font-size:14px;margin-bottom:20px">')
```

Insert before it:
```python
    # Greeting
    short_id = _short_entity_id(entity_id)
    operator = actor_name if actor_name else "System"
    action = _describe_event(event_type, event_key)
    greeting = f"<p style=\"margin:0 0 16px 0;font-family:Arial,sans-serif;font-size:14px;color:#333\">{operator} performed {action} on {type_label} {short_id}. Details below:</p>"

    # Table 1: Notification Info
    lines = []
    lines.append(greeting)
```

- [ ] **Step 2: Add greeting assertions to existing tests**

In `tests/test_notification_templates.py`, in `TestBuildBody`, update `test_sc_body_shows_sc_fields` to also verify the greeting:

```python
    def test_sc_body_shows_sc_fields(self):
        entry = {
            "entity_type": "sc",
            "entity_id": "SC-V2SE7PP-20260629-002",
            "event_type": "status_change",
            "event_key": "approve",
            "created_at": "2026-01-15T10:00:00Z",
        }
        entity_info = {
            "sc_no": "SC-2026-001",
            "sc_amount": 150000,
            "description": "IT equipment",
            "status": "approved",
        }
        body = templates.build_body(entry, entity_info, {})
        # Greeting
        assert "performed Approved on SC 0629-002" in body
        assert "Details below:" in body
        # Existing assertions
        assert "SC-2026-001" in body
        assert "Sc No" in body
        assert "150,000.00" in body
        assert "IT equipment" in body
        assert "Approved" in body
```

And add a dedicated test for the greeting:

```python
    def test_greeting_shows_operator_and_action(self):
        entry = {
            "entity_type": "gr",
            "entity_id": "GR-V2SE7PP-20260615-003",
            "event_type": "status_change",
            "event_key": "submit",
        }
        entity_info = {"gr_no": "GR-2026-003", "status": "manager_confirm"}
        body = templates.build_body(entry, entity_info, {}, actor_name="Li, Xingchen (C/EV-L)")
        assert "LiXingchen performed Submitted on GR 0615-003" in body

    def test_greeting_shows_system_when_no_actor(self):
        entry = {
            "entity_type": "po",
            "entity_id": "PO-001",
            "event_type": "threshold_date",
            "event_key": "threshold_date:3m",
        }
        entity_info = {"po_no": "PO-001", "status": "active"}
        body = templates.build_body(entry, entity_info, {})
        assert "System performed" in body
```

- [ ] **Step 3: Run tests to verify**

Run: `uv run pytest tests/test_notification_templates.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/notification/templates.py tests/test_notification_templates.py
git commit -m "feat: add greeting line to operational email body"
```

---

### Task 2: Configurable sender email

**Files:**
- Modify: `sc_gr_app/api/bridge.py` — add `get_sender_email` and `set_sender_email` methods
- Modify: `frontend/src/views/SystemView.vue` — add sender email input section
- Modify: `frontend/src/i18n/locales/en-US.js` — add translation keys
- Modify: `frontend/src/i18n/locales/zh-CN.js` — add translation keys
- Modify: `sc_gr_app/notification/sender.py` — read `notify.sender_email` and use `SendUsingAccount`

#### Task 2a: Backend APIs

- [ ] **Step 1: Add `get_sender_email` and `set_sender_email` to bridge.py**

In `sc_gr_app/api/bridge.py`, add after the `set_attachments_dir` method (around line 1265):

```python
    def get_sender_email(self, _payload=None) -> dict:
        """Return the configured notification sender email address."""
        try:
            from sc_gr_app.db.connection import connect
            with connect(self.config) as conn:
                row = conn.execute(
                    "SELECT setting_value FROM app_settings WHERE setting_key = 'notify.sender_email'"
                ).fetchone()
                return ok({"email": row["setting_value"] if row else ""})
        except Exception as exc:
            return fail(exc)

    def set_sender_email(self, payload) -> dict:
        """Set the notification sender email address."""
        try:
            from sc_gr_app.db.connection import connect
            from datetime import datetime, timezone
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            from sc_gr_app.rbac import require_admin
            require_admin(current_user)
            email = _require_payload_field(payload, "email")
            timestamp = datetime.now(timezone.utc).isoformat()
            with connect(self.config) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                    ("notify.sender_email", email.strip(), timestamp),
                )
                conn.commit()
            return ok({"email": email.strip()})
        except Exception as exc:
            return fail(exc)
```

- [ ] **Step 2: Add `SendUsingAccount` logic to `send_entry()`**

In `sc_gr_app/notification/sender.py`, in the `send_entry()` function, after `pythoncom.CoInitialize()` and before creating the mail item (around line 367), add account resolution:

Replace this block:
```python
    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)  # 0 = olMailItem
```

With:
```python
    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)  # 0 = olMailItem

        # Use configured sender account if available
        sender_email = conn.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = 'notify.sender_email'"
        ).fetchone()
        if sender_email and sender_email["setting_value"]:
            target = sender_email["setting_value"].strip().lower()
            for acc in outlook.Session.Accounts:
                if acc.SmtpAddress and acc.SmtpAddress.lower() == target:
                    mail.SendUsingAccount = acc
                    break
```

- [ ] **Step 3: Commit backend changes**

```bash
git add sc_gr_app/api/bridge.py sc_gr_app/notification/sender.py
git commit -m "feat: add sender email config API and SendUsingAccount support"
```

#### Task 2b: Frontend UI

- [ ] **Step 4: Add i18n keys**

In `frontend/src/i18n/locales/en-US.js`, find the `settings` section near line 737 and add:

```js
    senderEmail: 'Sender Email',
    senderEmailHint: 'Notification emails will be sent from this Outlook account. Leave empty to use the default account.',
```

In `frontend/src/i18n/locales/zh-CN.js`, find the corresponding `settings` section and add:

```js
    senderEmail: '发件邮箱',
    senderEmailHint: '通知邮件将使用此 Outlook 账户发送。留空则使用默认账户。',
```

- [ ] **Step 5: Add sender email section to SystemView.vue**

In `frontend/src/views/SystemView.vue`, add a new section after the Attachments Dir section (after line 71, before the Operation Logs section):

```html
    <div v-if="isAdmin" class="section-card">
      <div class="section-header">
        <h3>{{ $t('settings.senderEmail') }}</h3>
      </div>
      <div style="display:flex;align-items:center;gap:8px">
        <el-input v-model="senderEmail" :placeholder="'VGC.RS-POMP@audi.com'" style="flex:1" />
        <el-button type="primary" :disabled="senderEmail === savedSenderEmail" @click="handleSaveSenderEmail">
          {{ $t('common.save') }}
        </el-button>
      </div>
      <p style="color:#94a3b8;font-size:12px;margin-top:8px">{{ $t('settings.senderEmailHint') }}</p>
    </div>
```

In the `<script setup>` section, add the reactive state and methods (after the existing attachments dir code around line 287):

```js
// ── Sender email ──
const senderEmail = ref('')
const savedSenderEmail = ref('')

async function fetchSenderEmail() {
  try {
    const result = await callApi('get_sender_email')
    senderEmail.value = result.email || ''
    savedSenderEmail.value = result.email || ''
  } catch { senderEmail.value = ''; savedSenderEmail.value = '' }
}

async function handleSaveSenderEmail() {
  try {
    const result = await callApi('set_sender_email', { email: senderEmail.value })
    savedSenderEmail.value = result.email
    ElMessage.success(t('common.saved'))
  } catch (e) { ElMessage.error(e.message) }
}
```

Add `fetchSenderEmail()` to the `onMounted` call:

```js
onMounted(() => {
  if (isAdmin.value) { fetchUsers(); searchLogs() }
  fetchAttachmentsDir()
  fetchSenderEmail()
})
```

- [ ] **Step 6: Commit frontend changes**

```bash
git add frontend/src/views/SystemView.vue frontend/src/i18n/locales/en-US.js frontend/src/i18n/locales/zh-CN.js
git commit -m "feat: add sender email configuration UI in system settings"
```

---

### Task 3: Remove console window from notification executable

**Files:**
- Modify: `packaging/notification.spec` — line 40

- [ ] **Step 1: Change `console=True` to `console=False`**

In `packaging/notification.spec`, line 40:

```python
-    console=True,
+    console=False,
```

- [ ] **Step 2: Commit**

```bash
git add packaging/notification.spec
git commit -m "fix: disable console window in notification exe to prevent OpenConsole residue"
```

---

### Verification

- [ ] **Verify Task 1:** Run `uv run pytest tests/test_notification_templates.py -v` — all tests pass, greeting assertions included
- [ ] **Verify Task 2:** Start the dev server, navigate to System page as admin, set sender email, save — verify `app_settings` row is written. Then trigger a notification and check Outlook sent item uses the configured account.
- [ ] **Verify Task 3:** Rebuild notification exe with `powershell -ExecutionPolicy Bypass -File packaging/build.ps1`, run it manually — confirm no console window appears. Check Task Manager for no OpenConsole.exe.
