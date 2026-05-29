# Email Notification System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a two-part email notification system: desktop-side queue writer for status changes, and a standalone notification script (Outlook COM + scheduled task) for sending emails and daily threshold checks.

**Architecture:** The desktop app writes `notification_queue` rows inside existing write transactions. A separate Python script (`sc_gr_app/notification/`) polls the queue every 5 minutes, sends via win32com Outlook, and runs daily threshold checks (date/amount) on active SCs. Configuration lives in `notification_config` (per-SC), `notification_sent_threshold` (dedup), and `app_settings` (global defaults).

**Tech Stack:** Python 3.11, SQLite, win32com (Outlook via pywin32), pytest, Vue 3 + Element Plus

**Prerequisites:** Add `pywin32>=306` to `pyproject.toml` dependencies (needed for `win32com.client` in the notification script).

**Sender tests note:** `tests/test_notification_sender.py` is listed for reference but not included as a separate task — the sender module requires Outlook COM which is unavailable in CI. Sender behavior is verified manually via `--run-once` mode.

---

## File Structure

```
New files:
  sc_gr_app/services/notification_service.py    # queue writer + config CRUD
  sc_gr_app/notification/__init__.py            # (empty)
  sc_gr_app/notification/__main__.py            # CLI entry point
  sc_gr_app/notification/engine.py              # poll loop orchestration
  sc_gr_app/notification/sender.py              # Outlook COM email sender
  sc_gr_app/notification/queue.py               # queue read/write helpers
  sc_gr_app/notification/thresholds.py          # daily threshold check logic
  sc_gr_app/notification/config.py              # config reader (merges defaults + per-SC)
  sc_gr_app/notification/templates.py           # email subject/body (Chinese)
  tests/test_notification_service.py            # queue writer + config tests
  tests/test_notification_thresholds.py         # threshold logic tests
  tests/test_notification_sender.py             # sender tests (mocked Outlook)
  frontend/src/composables/useNotification.js   # notification API composable
  frontend/src/components/notification/ScNotificationCard.vue  # per-SC config card
  frontend/src/components/notification/NotificationDefaults.vue # system settings card

Modified files:
  sc_gr_app/db/migrations.py                    # add v3 migration
  sc_gr_app/api/bridge.py                       # add 5 new endpoints
  sc_gr_app/services/sc_service.py              # add notification calls to submit/approve/deny/close
  sc_gr_app/services/po_service.py              # add notification calls to create/approve/finish
  sc_gr_app/services/gr_service.py              # add notification calls to create/approve/cancel
  frontend/src/views/ScDetailView.vue           # add ScNotificationCard below Audit card
  frontend/src/views/SystemView.vue             # add NotificationDefaults card
```

---

### Task 1: Database Migration v3

**Files:**
- Modify: `sc_gr_app/db/migrations.py`

- [ ] **Step 1: Read the current migrations.py**

The file currently has `SCHEMA_VERSION = 2` and functions `migrate()`, `_migrate_v1()`, `_migrate_v2()`, helper methods. We add `_migrate_v3()` and update the version.

- [ ] **Step 2: Add the v3 migration function and update SCHEMA_VERSION**

```python
# Change line 1:
SCHEMA_VERSION = 3
```

Add the following function before `migrate()`:

```python
def _migrate_v3(conn) -> None:
    # notification_queue: pending email tasks for the notification script
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notification_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_key TEXT NOT NULL,
            to_recipients TEXT NOT NULL,
            cc_recipients TEXT NOT NULL,
            created_at TEXT NOT NULL,
            sent_at TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            error_msg TEXT,
            UNIQUE(entity_type, entity_id, event_key, status)
        )
    """)

    # notification_config: per-SC notification strategy
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notification_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL DEFAULT 'sc',
            entity_id TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            cc_user_ids TEXT NOT NULL DEFAULT '[]',
            date_thresholds TEXT NOT NULL DEFAULT '[]',
            amount_thresholds TEXT NOT NULL DEFAULT '[]',
            UNIQUE(entity_type, entity_id)
        )
    """)

    # notification_sent_threshold: dedup tracker (each threshold fires once per SC)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notification_sent_threshold (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            event_key TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            UNIQUE(entity_type, entity_id, event_key)
        )
    """)

    # Default notification settings
    defaults = [
        (
            "notify.admin_recipients",
            "[]",
        ),
        (
            "notify.transitions.sc",
            '{"submit":{"to":["notify.admin_recipients"],"cc":["requester"]},'
            '"approve":{"to":["requester"],"cc":["actor"]},'
            '"deny":{"to":["requester"],"cc":["actor"]},'
            '"close":{"to":["requester","notify.admin_recipients"],"cc":[]}}',
        ),
        (
            "notify.transitions.po",
            '{"create":{"to":["notify.admin_recipients"],"cc":["requester"]},'
            '"approve":{"to":["requester"],"cc":["actor"]},'
            '"finish":{"to":["requester","notify.admin_recipients"],"cc":[]}}',
        ),
        (
            "notify.transitions.gr",
            '{"create":{"to":["notify.admin_recipients"],"cc":["requester"]},'
            '"approve":{"to":["requester"],"cc":["actor"]},'
            '"cancel":{"to":["requester","notify.admin_recipients"],"cc":[]}}',
        ),
        ("notify.default_cc", "[]"),
        ("notify.default_date_thresholds", "[6, 3, 1, 0.5]"),
        ("notify.default_amount_thresholds", "[50, 30, 10]"),
    ]
    timestamp = utc_now()
    for key, value in defaults:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
            (key, value, timestamp),
        )

    _record(conn, 3)
```

Add the v3 block in `migrate()` after the v2 block:

```python
def migrate(config: AppConfig) -> None:
    with connect(config) as conn:
        try:
            applied = _applied_versions(conn)
            if 1 not in applied:
                conn.execute("BEGIN")
                _migrate_v1(conn)
                conn.commit()
            if 2 not in _applied_versions(conn):
                conn.execute("PRAGMA foreign_keys = OFF")
                conn.execute("PRAGMA legacy_alter_table = ON")
                conn.execute("BEGIN")
                _migrate_v2(conn)
                conn.commit()
                conn.execute("PRAGMA legacy_alter_table = OFF")
                conn.execute("PRAGMA foreign_keys = ON")
            elif not _sc_records_has_v2_constraints(conn):
                conn.execute("PRAGMA foreign_keys = OFF")
                conn.execute("PRAGMA legacy_alter_table = ON")
                conn.execute("BEGIN")
                _migrate_v2(conn)
                conn.commit()
                conn.execute("PRAGMA legacy_alter_table = OFF")
                conn.execute("PRAGMA foreign_keys = ON")
            # NEW v3 block:
            if 3 not in _applied_versions(conn):
                conn.execute("BEGIN")
                _migrate_v3(conn)
                conn.commit()
        except Exception:
            conn.rollback()
            ...
            raise
```

- [ ] **Step 3: Run migration tests to verify**

Run: `uv run pytest tests/test_migrations.py -v`
Expected: All tests pass, including any new assertions about v3 tables.

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/db/migrations.py
git commit -m "feat: add v3 migration — notification_queue, notification_config, notification_sent_threshold tables"
```

---

### Task 2: Notification Service (Queue Writer + Config CRUD)

**Files:**
- Create: `sc_gr_app/services/notification_service.py`

- [ ] **Step 1: Create the notification_service.py module**

```python
import json
import time

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import AppError


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class QueueWriteError(AppError):
    code = "QUEUE_WRITE_ERROR"


def _read_app_setting(conn, key):
    row = conn.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,)
    ).fetchone()
    return json.loads(row["setting_value"]) if row else None


def _resolve_keyword(keyword, entity, current_user):
    """Resolve a single recipient keyword to a list of user IDs."""
    if keyword == "requester":
        requester_id = entity.get("requester_id")
        return [requester_id] if requester_id else []
    if keyword == "actor":
        return [current_user["user_id"]]
    if keyword == "notify.admin_recipients":
        return []
    return [keyword]


def resolve_recipients(conn, rule_to_or_cc, entity, current_user):
    """Resolve a to/cc rule array to a list of user IDs.

    Keywords: 'requester', 'actor', 'notify.admin_recipients', or direct user IDs.
    'notify.admin_recipients' is looked up from app_settings at resolve time.
    """
    result = []
    for item in rule_to_or_cc:
        if item == "notify.admin_recipients":
            admin_setting = _read_app_setting(conn, "notify.admin_recipients")
            if admin_setting:
                result.extend(admin_setting)
        else:
            resolved = _resolve_keyword(item, entity, current_user)
            result.extend(resolved)
    # Deduplicate preserving order
    seen = set()
    unique = []
    for uid in result:
        if uid and uid not in seen:
            seen.add(uid)
            unique.append(uid)
    return unique


def queue_status_change(conn, entity_type, entity_id, transition, entity, current_user):
    """Insert a notification queue entry into the current transaction.

    Args:
        conn: Active sqlite3 connection (inside BEGIN IMMEDIATE)
        entity_type: 'sc' / 'po' / 'gr'
        entity_id: The entity's ID
        transition: 'submit' / 'approve' / 'deny' / 'close' / 'create' / 'finish' / 'cancel'
        entity: The entity dict (sc_record / po / gr) — used for requester_id
        current_user: The user dict performing the action — used for actor
    """
    transitions_key = f"notify.transitions.{entity_type}"
    rules_json = _read_app_setting(conn, transitions_key)
    if not rules_json:
        return  # No rules configured, skip notification

    rules = rules_json.get(transition)
    if not rules:
        return  # No rule for this transition

    to_rule = rules.get("to", [])
    cc_rule = rules.get("cc", [])

    to_ids = resolve_recipients(conn, to_rule, entity, current_user)
    cc_ids = resolve_recipients(conn, cc_rule, entity, current_user)

    # Merge per-SC CC list
    if entity_type == "sc":
        config_row = conn.execute(
            "SELECT cc_user_ids FROM notification_config WHERE entity_type = 'sc' AND entity_id = ? AND enabled = 1",
            (entity_id,),
        ).fetchone()
        if config_row:
            extra_cc = json.loads(config_row["cc_user_ids"])
            for uid in extra_cc:
                if uid and uid not in cc_ids:
                    cc_ids.append(uid)

    # Merge default CC list
    default_cc = _read_app_setting(conn, "notify.default_cc")
    if default_cc:
        for uid in default_cc:
            if uid and uid not in cc_ids:
                cc_ids.append(uid)

    # Remove primary recipients from CC
    cc_ids = [uid for uid in cc_ids if uid not in to_ids]

    if not to_ids:
        return  # Nobody to notify

    timestamp = _utc_now()
    conn.execute(
        """
        INSERT OR IGNORE INTO notification_queue
            (entity_type, entity_id, event_type, event_key, to_recipients, cc_recipients, created_at)
        VALUES (?, ?, 'status_change', ?, ?, ?, ?)
        """,
        (entity_type, entity_id, transition, json.dumps(to_ids), json.dumps(cc_ids), timestamp),
    )


def get_sc_notification_config(config: AppConfig, sc_id: str) -> dict | None:
    with connect(config) as conn:
        row = conn.execute(
            "SELECT enabled, cc_user_ids, date_thresholds, amount_thresholds "
            "FROM notification_config WHERE entity_type = 'sc' AND entity_id = ?",
            (sc_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "enabled": bool(row["enabled"]),
            "cc_user_ids": json.loads(row["cc_user_ids"]),
            "date_thresholds": json.loads(row["date_thresholds"]),
            "amount_thresholds": json.loads(row["amount_thresholds"]),
        }


def save_sc_notification_config(config: AppConfig, sc_id: str, data: dict) -> None:
    with connect(config) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """
                INSERT INTO notification_config (entity_type, entity_id, enabled, cc_user_ids, date_thresholds, amount_thresholds)
                VALUES ('sc', ?, ?, ?, ?, ?)
                ON CONFLICT(entity_type, entity_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    cc_user_ids = excluded.cc_user_ids,
                    date_thresholds = excluded.date_thresholds,
                    amount_thresholds = excluded.amount_thresholds
                """,
                (
                    sc_id,
                    1 if data.get("enabled", True) else 0,
                    json.dumps(data.get("cc_user_ids", [])),
                    json.dumps(data.get("date_thresholds", [])),
                    json.dumps(data.get("amount_thresholds", [])),
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def get_notification_defaults(config: AppConfig) -> dict:
    with connect(config) as conn:
        keys = [
            "notify.admin_recipients",
            "notify.transitions.sc",
            "notify.transitions.po",
            "notify.transitions.gr",
            "notify.default_cc",
            "notify.default_date_thresholds",
            "notify.default_amount_thresholds",
        ]
        result = {}
        for key in keys:
            row = conn.execute(
                "SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,)
            ).fetchone()
            result[key] = json.loads(row["setting_value"]) if row else None
        return result


def save_notification_defaults(config: AppConfig, data: dict) -> None:
    field_map = {
        "admin_recipients": "notify.admin_recipients",
        "transitions": None,  # handled separately
        "default_cc": "notify.default_cc",
        "date_thresholds": "notify.default_date_thresholds",
        "amount_thresholds": "notify.default_amount_thresholds",
    }
    with connect(config) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            timestamp = _utc_now()
            for data_key, setting_key in field_map.items():
                if setting_key and data_key in data:
                    conn.execute(
                        "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                        (setting_key, json.dumps(data[data_key]), timestamp),
                    )
            if "transitions" in data:
                transitions = data["transitions"]
                for entity_type in ("sc", "po", "gr"):
                    key = f"notify.transitions.{entity_type}"
                    if entity_type in transitions:
                        conn.execute(
                            "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                            (key, json.dumps(transitions[entity_type]), timestamp),
                        )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def list_notification_queue(
    config: AppConfig, sc_id: str | None = None, status: str | None = None,
    limit: int = 50, offset: int = 0,
) -> dict:
    with connect(config) as conn:
        conditions = []
        params = []
        if sc_id:
            conditions.append("entity_id = ?")
            params.append(sc_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        count_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM notification_queue {where}", params
        ).fetchone()
        rows = conn.execute(
            f"SELECT * FROM notification_queue {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return {
            "items": [dict(r) for r in rows],
            "total": count_row["cnt"],
        }
```

- [ ] **Step 2: Commit**

```bash
git add sc_gr_app/services/notification_service.py
git commit -m "feat: add notification_service — queue writer and config CRUD"
```

---

### Task 3: Integrate Notification into SC/PO/GR Services

**Files:**
- Modify: `sc_gr_app/services/sc_service.py`
- Modify: `sc_gr_app/services/po_service.py`
- Modify: `sc_gr_app/services/gr_service.py`

- [ ] **Step 1: Add notification call to sc_service.submit_sc()**

In `sc_gr_app/services/sc_service.py`, add the import at the top:

```python
from sc_gr_app.services import notification_service
```

In `submit_sc()`, after the `write_audit_log(...)` call (line 400) and before `conn.commit()` (line 411), add:

```python
                notification_service.queue_status_change(
                    conn, "sc", sc_id, "submit", before, current_user
                )
```

- [ ] **Step 2: Add notification call to sc_service.approve_sc()**

In `approve_sc()`, after `write_audit_log(...)` and before `conn.commit()`, add:

```python
                notification_service.queue_status_change(
                    conn, "sc", sc_id, "approve", before, current_user
                )
```

- [ ] **Step 3: Add notification call to sc_service.deny_sc()**

In `deny_sc()`, after `write_audit_log(...)` and before `conn.commit()`, add:

```python
                notification_service.queue_status_change(
                    conn, "sc", sc_id, "deny", before, current_user
                )
```

- [ ] **Step 4: Add notification call to sc_service.close_sc()**

In `close_sc()`, after `write_audit_log(...)` and before `conn.commit()`, add:

```python
                notification_service.queue_status_change(
                    conn, "sc", sc_id, "close", before, current_user
                )
```

- [ ] **Step 5: Add notification to po_service.create_po()**

In `sc_gr_app/services/po_service.py`, add the import:

```python
from sc_gr_app.services import notification_service
```

In `create_po()`, after `write_audit_log(...)` and before `conn.commit()`, add:

```python
                notification_service.queue_status_change(
                    conn, "po", po_id, "create", {"requester_id": sc["requester_id"]}, current_user
                )
```

Note: PO doesn't have its own `requester_id`, so we use the parent SC's `requester_id`.

- [ ] **Step 6: Add notification to po_service.approve_po()**

In `approve_po()`, after `write_audit_log(...)` and before `conn.commit()`, add:

```python
                sc = conn.execute("SELECT requester_id FROM sc_records WHERE sc_id = ?", (before["sc_id"],)).fetchone()
                notification_service.queue_status_change(
                    conn, "po", po_id, "approve",
                    {"requester_id": sc["requester_id"]} if sc else {}, current_user
                )
```

- [ ] **Step 7: Add notification to po_service.finish_po()**

In `finish_po()`, after `write_audit_log(...)` and before `conn.commit()`, add:

```python
                sc = conn.execute("SELECT requester_id FROM sc_records WHERE sc_id = ?", (before["sc_id"],)).fetchone()
                notification_service.queue_status_change(
                    conn, "po", po_id, "finish",
                    {"requester_id": sc["requester_id"]} if sc else {}, current_user
                )
```

- [ ] **Step 8: Add notification to gr_service.create_gr()**

Check `sc_gr_app/services/gr_service.py` for the `create_gr` function name. Add import and notification call after `write_audit_log(...)` and before `conn.commit()`:

```python
                notification_service.queue_status_change(
                    conn, "gr", gr_id, "create", {"requester_id": sc["requester_id"]}, current_user
                )
```

- [ ] **Step 9: Add notification to gr_service.approve_gr()**

After `write_audit_log(...)` and before `conn.commit()` in `approve_gr()`:

```python
                sc = conn.execute("SELECT requester_id FROM sc_records WHERE sc_id = ?", (before["sc_id"],)).fetchone()
                notification_service.queue_status_change(
                    conn, "gr", gr_id, "approve",
                    {"requester_id": sc["requester_id"]} if sc else {}, current_user
                )
```

- [ ] **Step 10: Add notification to gr_service.cancel_gr()**

After `write_audit_log(...)` and before `conn.commit()` in `cancel_gr()`:

```python
                sc = conn.execute("SELECT requester_id FROM sc_records WHERE sc_id = ?", (before["sc_id"],)).fetchone()
                notification_service.queue_status_change(
                    conn, "gr", gr_id, "cancel",
                    {"requester_id": sc["requester_id"]} if sc else {}, current_user
                )
```

- [ ] **Step 11: Run existing tests to verify no regressions**

Run: `uv run pytest tests/test_sc_po_gr_flow.py tests/test_api_bridge.py -v`
Expected: All passing — notification writes fail silently when config doesn't exist (they return early since no rules configured in test DBs).

- [ ] **Step 12: Commit**

```bash
git add sc_gr_app/services/sc_service.py sc_gr_app/services/po_service.py sc_gr_app/services/gr_service.py
git commit -m "feat: integrate notification queue writes into SC/PO/GR service transactions"
```

---

### Task 4: API Bridge Endpoints

**Files:**
- Modify: `sc_gr_app/api/bridge.py`

- [ ] **Step 1: Add 5 notification endpoints to ApiBridge**

In `sc_gr_app/api/bridge.py`, add the import:

```python
from sc_gr_app.services import notification_service
```

Add these methods to the `ApiBridge` class:

```python
    def get_sc_notification_config(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            return ok(notification_service.get_sc_notification_config(self.config, sc_id))
        except Exception as exc:
            return fail(exc)

    def save_sc_notification_config(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            data = _require_payload_field(payload, "data")
            notification_service.save_sc_notification_config(self.config, sc_id, data)
            return ok()
        except Exception as exc:
            return fail(exc)

    def get_notification_defaults(self, payload=None) -> dict:
        try:
            current_user = self._require_current_user()
            from sc_gr_app.rbac import require_admin
            require_admin(current_user)
            return ok(notification_service.get_notification_defaults(self.config))
        except Exception as exc:
            return fail(exc)

    def save_notification_defaults(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            from sc_gr_app.rbac import require_admin
            require_admin(current_user)
            data = _require_payload_field(payload, "data")
            notification_service.save_notification_defaults(self.config, data)
            return ok()
        except Exception as exc:
            return fail(exc)

    def list_notification_queue(self, payload=None) -> dict:
        try:
            payload = self._payload(payload) or {}
            current_user = self._require_current_user()
            return ok(notification_service.list_notification_queue(
                self.config,
                sc_id=payload.get("sc_id"),
                status=payload.get("status"),
                limit=payload.get("limit", 50),
                offset=payload.get("offset", 0),
            ))
        except Exception as exc:
            return fail(exc)
```

- [ ] **Step 2: Commit**

```bash
git add sc_gr_app/api/bridge.py
git commit -m "feat: add notification API endpoints to bridge"
```

---

### Task 5: Frontend — Notification Composable

**Files:**
- Create: `frontend/src/composables/useNotification.js`

- [ ] **Step 1: Create useNotification.js**

```javascript
import { reactive, readonly } from 'vue'
import { callApi } from '@/api/bridge.js'

export function useNotification() {
  const state = reactive({
    scConfig: null,
    scConfigLoading: false,
    scConfigError: null,
    defaults: null,
    defaultsLoading: false,
    defaultsError: null,
    queue: [],
    queueTotal: 0,
    queueLoading: false,
    queueError: null
  })

  async function fetchScConfig(scId) {
    state.scConfigLoading = true
    state.scConfigError = null
    try {
      state.scConfig = await callApi('get_sc_notification_config', { sc_id: scId })
    } catch (e) {
      state.scConfigError = e.message
      state.scConfig = null
    } finally {
      state.scConfigLoading = false
    }
  }

  async function saveScConfig(scId, data) {
    await callApi('save_sc_notification_config', { sc_id: scId, data })
    state.scConfig = data
  }

  async function fetchDefaults() {
    state.defaultsLoading = true
    state.defaultsError = null
    try {
      state.defaults = await callApi('get_notification_defaults', {})
    } catch (e) {
      state.defaultsError = e.message
      state.defaults = null
    } finally {
      state.defaultsLoading = false
    }
  }

  async function saveDefaults(data) {
    await callApi('save_notification_defaults', { data })
    state.defaults = data
  }

  async function fetchQueue({ scId, status, limit = 50, offset = 0 } = {}) {
    state.queueLoading = true
    state.queueError = null
    try {
      const result = await callApi('list_notification_queue', { sc_id: scId, status, limit, offset })
      state.queue = result.items
      state.queueTotal = result.total
    } catch (e) {
      state.queueError = e.message
      state.queue = []
      state.queueTotal = 0
    } finally {
      state.queueLoading = false
    }
  }

  return {
    state: readonly(state),
    fetchScConfig,
    saveScConfig,
    fetchDefaults,
    saveDefaults,
    fetchQueue
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/composables/useNotification.js
git commit -m "feat: add useNotification composable"
```

---

### Task 6: Frontend — SC Detail Notification Card

**Files:**
- Create: `frontend/src/components/notification/ScNotificationCard.vue`
- Modify: `frontend/src/views/ScDetailView.vue`

- [ ] **Step 1: Create ScNotificationCard.vue**

```vue
<template>
  <div class="section-card">
    <div class="section-header">
      <h3>Notification Settings</h3>
      <el-switch v-model="local.enabled" @change="emitSave" />
    </div>
    <template v-if="local.enabled">
      <div style="margin-top:12px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">CC List</label>
        <el-select
          v-model="local.cc_user_ids"
          multiple
          filterable
          placeholder="Select users to CC"
          style="width:100%"
          @change="emitSave"
        >
          <el-option
            v-for="u in users"
            :key="u.user_id"
            :label="`${u.user_name} -- ${u.machine_id}`"
            :value="u.user_id"
          />
        </el-select>
      </div>
      <div style="margin-top:12px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">Date Thresholds</label>
        <el-checkbox-group v-model="local.date_thresholds" @change="emitSave">
          <el-checkbox :label="6">6 months</el-checkbox>
          <el-checkbox :label="3">3 months</el-checkbox>
          <el-checkbox :label="1">1 month</el-checkbox>
          <el-checkbox :label="0.5">2 weeks</el-checkbox>
        </el-checkbox-group>
      </div>
      <div style="margin-top:12px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">Amount Thresholds</label>
        <el-checkbox-group v-model="local.amount_thresholds" @change="emitSave">
          <el-checkbox :label="50">50%</el-checkbox>
          <el-checkbox :label="30">30%</el-checkbox>
          <el-checkbox :label="10">10%</el-checkbox>
        </el-checkbox-group>
      </div>
    </template>
  </div>
</template>

<script setup>
import { reactive, watch, onMounted } from 'vue'

const props = defineProps({
  scId: { type: String, required: true },
  config: { type: Object, default: null },
  users: { type: Array, default: () => [] }
})

const emit = defineEmits(['save'])

const local = reactive({
  enabled: true,
  cc_user_ids: [],
  date_thresholds: [],
  amount_thresholds: []
})

watch(() => props.config, (val) => {
  if (val) {
    local.enabled = val.enabled
    local.cc_user_ids = val.cc_user_ids || []
    local.date_thresholds = val.date_thresholds || []
    local.amount_thresholds = val.amount_thresholds || []
  }
}, { immediate: true })

function emitSave() {
  emit('save', { ...local })
}
</script>
```

- [ ] **Step 2: Integrate card into ScDetailView.vue**

In `ScDetailView.vue`, add below the Audit Log card (the third `section-card`):

```vue
      <ScNotificationCard
        v-if="detail.sc"
        :sc-id="detail.sc.sc_id"
        :config="notificationConfig"
        :users="users"
        @save="handleNotificationSave"
      />
```

Add the import:

```javascript
import ScNotificationCard from '@/components/notification/ScNotificationCard.vue'
import { useNotification } from '@/composables/useNotification.js'
```

Add composable usage in `<script setup>`:

```javascript
const { state: notifState, fetchScConfig, saveScConfig } = useNotification()
const notificationConfig = computed(() => notifState.scConfig)

onMounted(async () => {
  if (scId.value) {
    await fetchScConfig(scId.value)
  }
})

async function handleNotificationSave(data) {
  try {
    await saveScConfig(scId.value, data)
    ElMessage.success('Notification settings saved')
  } catch (e) {
    ElMessage.error('Failed to save notification settings')
  }
}
```

Replace the existing `const users` in `ScDetailView.vue` with a shared reactive reference so it can be passed to the card. Ensure `users` is fetched in `onMounted` and passed as prop.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/notification/ScNotificationCard.vue frontend/src/views/ScDetailView.vue
git commit -m "feat: add per-SC notification settings card to SC detail view"
```

---

### Task 7: Frontend — System Settings Notification Defaults

**Files:**
- Create: `frontend/src/components/notification/NotificationDefaults.vue`
- Modify: `frontend/src/views/SystemView.vue`

- [ ] **Step 1: Create NotificationDefaults.vue**

```vue
<template>
  <div class="section-card">
    <h3 style="margin-bottom:12px">Notification Defaults</h3>

    <div v-if="loading">Loading...</div>
    <template v-else>
      <!-- Admin Recipients -->
      <div style="margin-bottom:16px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">Admin Recipients</label>
        <el-select
          v-model="local.admin_recipients"
          multiple
          filterable
          placeholder="Select admins who receive notifications"
          style="width:100%"
          @change="emitSave"
        >
          <el-option
            v-for="u in adminUsers"
            :key="u.user_id"
            :label="`${u.user_name} -- ${u.machine_id}`"
            :value="u.user_id"
          />
        </el-select>
      </div>

      <!-- Transition Rules -->
      <div style="margin-bottom:16px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">SC Transition Rules</label>
        <el-table :data="transitionRows('sc')" border size="small">
          <el-table-column prop="transition" label="Transition" width="100" />
          <el-table-column label="To" width="200">
            <template #default="{ row }">
              <el-select v-model="local.transitions.sc[row.transition].to" multiple filterable
                style="width:100%" @change="emitSave">
                <el-option label="Admin Recipients" value="notify.admin_recipients" />
                <el-option label="Requester" value="requester" />
                <el-option label="Actor" value="actor" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="CC" width="200">
            <template #default="{ row }">
              <el-select v-model="local.transitions.sc[row.transition].cc" multiple filterable
                style="width:100%" @change="emitSave">
                <el-option label="Admin Recipients" value="notify.admin_recipients" />
                <el-option label="Requester" value="requester" />
                <el-option label="Actor" value="actor" />
              </el-select>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- Default CC -->
      <div style="margin-bottom:16px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">Default CC List</label>
        <el-select v-model="local.default_cc" multiple filterable
          placeholder="Select users" style="width:100%" @change="emitSave">
          <el-option v-for="u in allUsers" :key="u.user_id"
            :label="`${u.user_name} -- ${u.machine_id}`" :value="u.user_id" />
        </el-select>
      </div>

      <!-- Thresholds -->
      <div style="margin-bottom:16px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">Default Date Thresholds</label>
        <el-checkbox-group v-model="local.date_thresholds" @change="emitSave">
          <el-checkbox :label="6">6 months</el-checkbox>
          <el-checkbox :label="3">3 months</el-checkbox>
          <el-checkbox :label="1">1 month</el-checkbox>
          <el-checkbox :label="0.5">2 weeks</el-checkbox>
        </el-checkbox-group>
      </div>
      <div>
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">Default Amount Thresholds</label>
        <el-checkbox-group v-model="local.amount_thresholds" @change="emitSave">
          <el-checkbox :label="50">50%</el-checkbox>
          <el-checkbox :label="30">30%</el-checkbox>
          <el-checkbox :label="10">10%</el-checkbox>
        </el-checkbox-group>
      </div>
    </template>
  </div>
</template>

<script setup>
import { reactive, watch, computed } from 'vue'

const props = defineProps({
  defaults: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  users: { type: Array, default: () => [] }
})

const emit = defineEmits(['save'])

const adminUsers = computed(() => props.users.filter(u => u.role === 'admin'))

const local = reactive({
  admin_recipients: [],
  transitions: {
    sc: { submit: { to: [], cc: [] }, approve: { to: [], cc: [] }, deny: { to: [], cc: [] }, close: { to: [], cc: [] } },
    po: { create: { to: [], cc: [] }, approve: { to: [], cc: [] }, finish: { to: [], cc: [] } },
    gr: { create: { to: [], cc: [] }, approve: { to: [], cc: [] }, cancel: { to: [], cc: [] } }
  },
  default_cc: [],
  date_thresholds: [],
  amount_thresholds: []
})

watch(() => props.defaults, (val) => {
  if (val) {
    local.admin_recipients = val['notify.admin_recipients'] || []
    local.transitions.sc = val['notify.transitions.sc'] || local.transitions.sc
    local.transitions.po = val['notify.transitions.po'] || local.transitions.po
    local.transitions.gr = val['notify.transitions.gr'] || local.transitions.gr
    local.default_cc = val['notify.default_cc'] || []
    local.date_thresholds = val['notify.default_date_thresholds'] || []
    local.amount_thresholds = val['notify.default_amount_thresholds'] || []
  }
}, { immediate: true })

function transitionRows(entityType) {
  return Object.keys(local.transitions[entityType]).map(t => ({
    transition: t
  }))
}

function emitSave() {
  emit('save', {
    admin_recipients: local.admin_recipients,
    transitions: local.transitions,
    default_cc: local.default_cc,
    date_thresholds: local.date_thresholds,
    amount_thresholds: local.amount_thresholds
  })
}
</script>
```

- [ ] **Step 2: Integrate into SystemView.vue**

In `SystemView.vue`, add below the User Management card:

```vue
    <NotificationDefaults
      v-if="isAdmin"
      :defaults="notifState.defaults"
      :loading="notifState.defaultsLoading"
      :users="state.users"
      @save="handleNotifDefaultsSave"
    />
```

Add import and composable usage:

```javascript
import NotificationDefaults from '@/components/notification/NotificationDefaults.vue'
import { useNotification } from '@/composables/useNotification.js'

const { state: notifState, fetchDefaults, saveDefaults } = useNotification()

onMounted(async () => {
  await fetchDefaults()
})

async function handleNotifDefaultsSave(data) {
  try {
    await saveDefaults(data)
    ElMessage.success('Notification defaults saved')
  } catch (e) {
    ElMessage.error('Failed to save notification defaults')
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/notification/NotificationDefaults.vue frontend/src/views/SystemView.vue
git commit -m "feat: add notification defaults configuration to system settings"
```

---

### Task 8: Notification Script — queue.py and config.py

**Files:**
- Create: `sc_gr_app/notification/__init__.py`
- Create: `sc_gr_app/notification/queue.py`
- Create: `sc_gr_app/notification/config.py`

- [ ] **Step 1: Create __init__.py (empty)**

```python
```

- [ ] **Step 2: Create queue.py**

```python
"""Read/write notification_queue. Shared pattern with desktop notification_service."""

import json
import sqlite3

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect


def fetch_pending(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM notification_queue WHERE status = 'pending' ORDER BY created_at ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_failed(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM notification_queue WHERE status = 'failed' ORDER BY created_at ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def mark_sent(conn: sqlite3.Connection, queue_id: int, timestamp: str) -> None:
    conn.execute(
        "UPDATE notification_queue SET status = 'sent', sent_at = ? WHERE id = ?",
        (timestamp, queue_id),
    )


def mark_failed(conn: sqlite3.Connection, queue_id: int, error_msg: str) -> None:
    conn.execute(
        "UPDATE notification_queue SET status = 'failed', error_msg = ? WHERE id = ?",
        (error_msg, queue_id),
    )


def queue_threshold(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: str,
    event_key: str,
    to_ids: list[str],
    cc_ids: list[str],
    timestamp: str,
) -> None:
    event_type = "threshold_date" if "date" in event_key else "threshold_amount"
    conn.execute(
        """
        INSERT OR IGNORE INTO notification_queue
            (entity_type, entity_id, event_type, event_key, to_recipients, cc_recipients, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (entity_type, entity_id, event_type, event_key, json.dumps(to_ids), json.dumps(cc_ids), timestamp),
    )


def is_threshold_sent(conn: sqlite3.Connection, entity_type: str, entity_id: str, event_key: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM notification_sent_threshold WHERE entity_type = ? AND entity_id = ? AND event_key = ?",
        (entity_type, entity_id, event_key),
    ).fetchone()
    return row is not None


def mark_threshold_sent(conn: sqlite3.Connection, entity_type: str, entity_id: str, event_key: str, timestamp: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO notification_sent_threshold (entity_type, entity_id, event_key, sent_at) VALUES (?, ?, ?, ?)",
        (entity_type, entity_id, event_key, timestamp),
    )
```

- [ ] **Step 3: Create config.py**

```python
"""Read notification configuration, merging defaults with per-SC overrides."""

import json
import sqlite3


def get_admin_recipients(conn: sqlite3.Connection) -> list[str]:
    row = conn.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key = 'notify.admin_recipients'"
    ).fetchone()
    return json.loads(row["setting_value"]) if row else []


def get_entity_config(conn: sqlite3.Connection, sc_id: str) -> dict | None:
    row = conn.execute(
        "SELECT enabled, cc_user_ids, date_thresholds, amount_thresholds "
        "FROM notification_config WHERE entity_type = 'sc' AND entity_id = ?",
        (sc_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "enabled": bool(row["enabled"]),
        "cc_user_ids": json.loads(row["cc_user_ids"]),
        "date_thresholds": json.loads(row["date_thresholds"]),
        "amount_thresholds": json.loads(row["amount_thresholds"]),
    }


def get_default_date_thresholds(conn: sqlite3.Connection) -> list:
    row = conn.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key = 'notify.default_date_thresholds'"
    ).fetchone()
    return json.loads(row["setting_value"]) if row else [6, 3, 1, 0.5]


def get_default_amount_thresholds(conn: sqlite3.Connection) -> list:
    row = conn.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key = 'notify.default_amount_thresholds'"
    ).fetchone()
    return json.loads(row["setting_value"]) if row else [50, 30, 10]
```

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/notification/__init__.py sc_gr_app/notification/queue.py sc_gr_app/notification/config.py
git commit -m "feat: add notification script — queue and config modules"
```

---

### Task 9: Notification Script — sender.py and templates.py

**Files:**
- Create: `sc_gr_app/notification/sender.py`
- Create: `sc_gr_app/notification/templates.py`

- [ ] **Step 1: Create templates.py**

```python
"""Email subject and body templates (Chinese)."""


def build_subject(entry: dict, entity_info: dict) -> str:
    entity_type = entry["entity_type"]
    entity_id = entry["entity_id"]
    event_key = entry["event_key"]

    type_label = {"sc": "SC", "po": "PO", "gr": "GR"}.get(entity_type, entity_type)

    if entry["event_type"] == "status_change":
        transition_labels = {
            "submit": "已提交",
            "create": "已创建",
            "approve": "已批准",
            "deny": "已拒绝",
            "close": "已关闭",
            "finish": "已完成",
            "cancel": "已取消",
        }
        label = transition_labels.get(event_key, event_key)
        return f"[Contract] {type_label} {entity_id} {label}"

    if entry["event_type"] == "threshold_date":
        sc_no = entity_info.get("sc_no") or entity_id
        months = event_key.replace("threshold_date:", "").replace("m", "")
        return f"[Contract] SC {sc_no} 合同即将到期 — 剩余不足{months}个月"

    if entry["event_type"] == "threshold_amount":
        sc_no = entity_info.get("sc_no") or entity_id
        pct = event_key.replace("threshold_amount:", "").replace("%", "")
        return f"[Contract] SC {sc_no} 预算即将耗尽 — 剩余不足{pct}%"

    return f"[Contract] {type_label} {entity_id} — {event_key}"


def build_body(entry: dict, entity_info: dict, user_emails: dict) -> str:
    entity_type = entry["entity_type"]
    entity_id = entry["entity_id"]

    type_label = {"sc": "SC", "po": "PO", "gr": "GR"}.get(entity_type, entity_type)
    sc_no = entity_info.get("sc_no", "") or ""
    sc_amount = entity_info.get("sc_amount", "") or ""
    description = entity_info.get("description", "") or ""
    status = entity_info.get("status", "") or ""

    lines = [
        f"<p>This is an automated notification from the Contract Management System.</p>",
        f"<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse'>",
        f"<tr><td><b>Type</b></td><td>{type_label}</td></tr>",
        f"<tr><td><b>ID</b></td><td>{entity_id}</td></tr>",
    ]
    if sc_no:
        lines.append(f"<tr><td><b>SC No</b></td><td>{sc_no}</td></tr>")
    if sc_amount:
        lines.append(f"<tr><td><b>Amount</b></td><td>{sc_amount}</td></tr>")
    if status:
        lines.append(f"<tr><td><b>Status</b></td><td>{status}</td></tr>")
    if description:
        lines.append(f"<tr><td><b>Description</b></td><td>{description}</td></tr>")

    lines.append(f"<tr><td><b>Event</b></td><td>{entry['event_key']}</td></tr>")
    lines.append(f"<tr><td><b>Time</b></td><td>{entry['created_at']}</td></tr>")
    lines.append(f"</table>")

    return "\n".join(lines)
```

- [ ] **Step 2: Create sender.py**

```python
"""Send email via Outlook COM (win32com)."""

import logging
import sqlite3

from sc_gr_app.notification import queue, templates

logger = logging.getLogger(__name__)


def resolve_emails(conn: sqlite3.Connection, user_ids: list[str]) -> dict[str, str]:
    """Map user IDs to email addresses from the users table."""
    if not user_ids:
        return {}
    placeholders = ",".join("?" * len(user_ids))
    rows = conn.execute(
        f"SELECT user_id, email FROM users WHERE user_id IN ({placeholders})",
        user_ids,
    ).fetchall()
    return {r["user_id"]: r["email"] for r in rows if r["email"]}


def send_entry(conn: sqlite3.Connection, entry: dict) -> bool:
    """Send a single queue entry via Outlook. Returns True on success."""
    import pythoncom
    import win32com.client

    to_ids = __import__("json").loads(entry["to_recipients"])
    cc_ids = __import__("json").loads(entry["cc_recipients"])

    to_emails_map = resolve_emails(conn, to_ids)
    cc_emails_map = resolve_emails(conn, cc_ids)

    to_addresses = [to_emails_map[uid] for uid in to_ids if uid in to_emails_map]
    cc_addresses = [cc_emails_map[uid] for uid in cc_ids if uid in cc_emails_map]

    if not to_addresses:
        logger.warning("No valid To addresses for queue entry %s, skipping", entry["id"])
        return False

    # Get entity info for the email body
    entity_type = entry["entity_type"]
    entity_id = entry["entity_id"]
    entity_info = {}
    if entity_type == "sc":
        row = conn.execute(
            "SELECT * FROM sc_records WHERE sc_id = ?", (entity_id,)
        ).fetchone()
    elif entity_type == "po":
        row = conn.execute(
            "SELECT * FROM pos WHERE po_id = ?", (entity_id,)
        ).fetchone()
    elif entity_type == "gr":
        row = conn.execute(
            "SELECT * FROM gr_requests WHERE gr_id = ?", (entity_id,)
        ).fetchone()
    else:
        row = None

    if row:
        entity_info = dict(row)

    subject = templates.build_subject(entry, entity_info)
    body = templates.build_body(entry, entity_info, {**to_emails_map, **cc_emails_map})

    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)  # 0 = olMailItem
        mail.Subject = subject
        mail.HTMLBody = body
        mail.To = "; ".join(to_addresses)
        if cc_addresses:
            mail.CC = "; ".join(cc_addresses)
        mail.Send()
        logger.info("Sent queue entry %s: %s", entry["id"], subject)
        return True
    finally:
        pythoncom.CoUninitialize()


def process_pending(conn: sqlite3.Connection) -> tuple[int, int]:
    """Send all pending queue entries. Returns (sent_count, failed_count)."""
    import json as _json
    from datetime import datetime, timezone

    entries = queue.fetch_pending(conn)
    sent = 0
    failed = 0
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for entry in entries:
        try:
            if send_entry(conn, entry):
                queue.mark_sent(conn, entry["id"], timestamp)
                sent += 1
            else:
                queue.mark_failed(conn, entry["id"], "No valid To addresses")
                failed += 1
        except Exception as exc:
            queue.mark_failed(conn, entry["id"], str(exc))
            failed += 1
            logger.error("Failed to send queue entry %s: %s", entry["id"], exc)

    return sent, failed


def process_failed(conn: sqlite3.Connection) -> tuple[int, int]:
    """Retry all failed queue entries. Returns (recovered_count, still_failed_count)."""
    from datetime import datetime, timezone

    entries = queue.fetch_failed(conn)
    recovered = 0
    still_failed = 0
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for entry in entries:
        try:
            if send_entry(conn, entry):
                queue.mark_sent(conn, entry["id"], timestamp)
                recovered += 1
            else:
                queue.mark_failed(conn, entry["id"], "No valid To addresses")
                still_failed += 1
        except Exception as exc:
            queue.mark_failed(conn, entry["id"], str(exc))
            still_failed += 1
            logger.error("Retry failed for queue entry %s: %s", entry["id"], exc)

    return recovered, still_failed
```

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/notification/templates.py sc_gr_app/notification/sender.py
git commit -m "feat: add notification script — Outlook sender and email templates"
```

---

### Task 10: Notification Script — thresholds.py

**Files:**
- Create: `sc_gr_app/notification/thresholds.py`

- [ ] **Step 1: Create thresholds.py**

```python
"""Daily threshold check: scan active SCs for date/amount thresholds."""

import json
import logging
import sqlite3
from datetime import datetime, timezone, date

from sc_gr_app.notification import queue as q
from sc_gr_app.notification import config as cfg

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check_all_active_scs(conn: sqlite3.Connection) -> tuple[int, int]:
    """Check all approved SCs for threshold breaches. Returns (date_events, amount_events)."""
    rows = conn.execute(
        "SELECT * FROM sc_records WHERE status = 'approved' AND service_period_end IS NOT NULL AND sc_amount IS NOT NULL"
    ).fetchall()

    admin_recipients = cfg.get_admin_recipients(conn)
    today = date.today()
    timestamp = _utc_now()
    date_count = 0
    amount_count = 0

    for sc in rows:
        sc_dict = dict(sc)
        sc_id = sc_dict["sc_id"]
        entity_config = cfg.get_entity_config(conn, sc_id)

        if entity_config is not None and not entity_config["enabled"]:
            continue  # Disabled per-SC

        # Merge thresholds: per-SC overrides defaults
        date_thresholds = (
            entity_config["date_thresholds"]
            if entity_config and entity_config.get("date_thresholds")
            else cfg.get_default_date_thresholds(conn)
        )
        amount_thresholds = (
            entity_config["amount_thresholds"]
            if entity_config and entity_config.get("amount_thresholds")
            else cfg.get_default_amount_thresholds(conn)
        )

        cc_ids = entity_config["cc_user_ids"] if entity_config else []
        requester_id = sc_dict["requester_id"]

        to_ids = [requester_id] + admin_recipients
        to_ids = list(dict.fromkeys([uid for uid in to_ids if uid]))  # dedup, remove None

        # Date check
        if sc_dict["service_period_end"]:
            try:
                end_date = date.fromisoformat(sc_dict["service_period_end"])
                remaining_days = (end_date - today).days

                for threshold_months in sorted(date_thresholds, reverse=True):
                    threshold_days = int(threshold_months * 30)
                    if remaining_days < threshold_days:
                        event_key = f"threshold_date:{threshold_months}m"
                        if not q.is_threshold_sent(conn, "sc", sc_id, event_key):
                            q.queue_threshold(conn, "sc", sc_id, event_key, to_ids, cc_ids, timestamp)
                            q.mark_threshold_sent(conn, "sc", sc_id, event_key, timestamp)
                            date_count += 1
                            logger.info("Date threshold triggered: SC %s, %s (remaining: %s days)",
                                        sc_id, event_key, remaining_days)
                        break  # Only fire tightest unmet threshold
            except (ValueError, TypeError):
                pass

        # Amount check
        sc_amount = sc_dict["sc_amount"]
        if sc_amount and sc_amount > 0:
            try:
                approved_gr_total_row = conn.execute(
                    """
                    SELECT COALESCE(SUM(gr.con_value), 0) as total
                    FROM gr_requests gr
                    WHERE gr.sc_id = ? AND gr.status = 'approved'
                    """,
                    (sc_id,),
                ).fetchone()
                spent = float(approved_gr_total_row["total"]) if approved_gr_total_row else 0.0
                remaining_pct = ((float(sc_amount) - spent) / float(sc_amount)) * 100

                for threshold_pct in sorted(amount_thresholds, reverse=True):
                    if remaining_pct < threshold_pct:
                        event_key = f"threshold_amount:{threshold_pct}%"
                        if not q.is_threshold_sent(conn, "sc", sc_id, event_key):
                            q.queue_threshold(conn, "sc", sc_id, event_key, to_ids, cc_ids, timestamp)
                            q.mark_threshold_sent(conn, "sc", sc_id, event_key, timestamp)
                            amount_count += 1
                            logger.info("Amount threshold triggered: SC %s, %s (remaining: %.1f%%)",
                                        sc_id, event_key, remaining_pct)
                        break  # Only fire tightest unmet threshold
            except (ValueError, TypeError, ZeroDivisionError):
                pass

    return date_count, amount_count
```

- [ ] **Step 2: Commit**

```bash
git add sc_gr_app/notification/thresholds.py
git commit -m "feat: add notification script — daily threshold check logic"
```

---

### Task 11: Notification Script — engine.py and __main__.py

**Files:**
- Create: `sc_gr_app/notification/engine.py`
- Create: `sc_gr_app/notification/__main__.py`

- [ ] **Step 1: Create engine.py**

```python
"""Poll loop orchestration for the notification script."""

import logging
import time
from datetime import datetime, timezone

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.notification import sender, thresholds

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_poll_loop(config: AppConfig, poll_interval: int = 300) -> None:
    """Run the notification poll loop indefinitely. Sends emails + periodic threshold checks.

    Args:
        config: AppConfig for DB access
        poll_interval: Seconds between pending queue checks (default 5 min)
    """
    last_threshold_check_date = None

    logger.info("Notification poll loop started. Poll interval: %ss", poll_interval)

    while True:
        try:
            with connect(config) as conn:
                # Process pending queue (every cycle)
                sent, failed = sender.process_pending(conn)
                if sent or failed:
                    logger.info("Pending queue: %s sent, %s failed", sent, failed)

                # Retry failed queue every 15 minutes (every 3rd cycle at 5min interval)
                # We check by tracking within the loop
                recovered, still_failed = sender.process_failed(conn)
                if recovered or still_failed:
                    logger.info("Failed retry: %s recovered, %s still failed", recovered, still_failed)

                # Threshold check once per day
                today = datetime.now(timezone.utc).date()
                if last_threshold_check_date != today:
                    conn.execute("BEGIN IMMEDIATE")
                    try:
                        date_count, amount_count = thresholds.check_all_active_scs(conn)
                        conn.commit()
                        if date_count or amount_count:
                            logger.info("Daily threshold check: %s date events, %s amount events",
                                        date_count, amount_count)
                        last_threshold_check_date = today
                    except Exception:
                        conn.rollback()
                        raise

                conn.commit()  # commit any remaining sender changes

        except Exception:
            logger.exception("Error in poll cycle")

        time.sleep(poll_interval)


def run_once(config: AppConfig) -> None:
    """Run one cycle: process pending + failed + threshold check. For testing/scheduling."""
    with connect(config) as conn:
        sent, failed = sender.process_pending(conn)
        logger.info("Pending: %s sent, %s failed", sent, failed)

        recovered, still_failed = sender.process_failed(conn)
        logger.info("Failed retry: %s recovered, %s still failed", recovered, still_failed)

        conn.execute("BEGIN IMMEDIATE")
        try:
            date_count, amount_count = thresholds.check_all_active_scs(conn)
            conn.commit()
            logger.info("Thresholds: %s date, %s amount", date_count, amount_count)
        except Exception:
            conn.rollback()
            raise

        conn.commit()


def run_thresholds_only(config: AppConfig) -> None:
    """Run only the threshold check. For scheduled daily run."""
    with connect(config) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            date_count, amount_count = thresholds.check_all_active_scs(conn)
            conn.commit()
            logger.info("Thresholds: %s date, %s amount", date_count, amount_count)
        except Exception:
            conn.rollback()
            raise
```

- [ ] **Step 2: Create __main__.py**

```python
"""Entry point for the notification script.

Usage:
    uv run python -m sc_gr_app.notification                    # poll loop (default: 5min)
    uv run python -m sc_gr_app.notification --poll-interval 60 # custom interval
    uv run python -m sc_gr_app.notification --run-once         # one cycle + exit
    uv run python -m sc_gr_app.notification --thresholds-only  # only threshold check
"""

import argparse
import logging
import sys

from sc_gr_app.config import default_config
from sc_gr_app.notification import engine

def main():
    parser = argparse.ArgumentParser(description="Email notification script")
    parser.add_argument("--poll-interval", type=int, default=300,
                        help="Seconds between queue checks (default: 300)")
    parser.add_argument("--run-once", action="store_true",
                        help="Run one cycle and exit")
    parser.add_argument("--thresholds-only", action="store_true",
                        help="Run only the threshold check and exit")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    config = default_config()
    logging.info("Using database: %s", config.db_path)

    if args.thresholds_only:
        engine.run_thresholds_only(config)
    elif args.run_once:
        engine.run_once(config)
    else:
        engine.run_poll_loop(config, poll_interval=args.poll_interval)

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify the module is importable**

Run: `uv run python -c "from sc_gr_app.notification import engine, sender, queue, thresholds, config, templates; print('All modules imported successfully')"`
Expected: "All modules imported successfully" (may error if win32com not available, that's OK for now).

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/notification/engine.py sc_gr_app/notification/__main__.py
git commit -m "feat: add notification script — engine and CLI entry point"
```

---

### Task 12: Tests — notification_service.py

**Files:**
- Create: `tests/test_notification_service.py`

- [ ] **Step 1: Create test_notification_service.py**

```python
"""Tests for notification_service — queue writer and config CRUD."""

import json

from sc_gr_app.services import notification_service
from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate


def _seed_user(conn, user_id, machine_id, role="requester", email=None):
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, machine_id, user_name, role, email, status) VALUES (?, ?, ?, ?, ?, 'active')",
        (user_id, machine_id, f"User {user_id}", role, email or f"{user_id}@test.com"),
    )


def _seed_sc(conn, sc_id, requester_id, status="approved", sc_amount=100000, service_period_end=None):
    conn.execute(
        """INSERT OR REPLACE INTO sc_records (sc_id, requester_id, status, request_type, cost_center,
           sc_amount, service_period_start, service_period_end, description, created_at, updated_at)
           VALUES (?, ?, ?, 'material', 'CC1', ?, '2025-01-01', ?, '', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')""",
        (sc_id, requester_id, status, sc_amount, service_period_end or "2026-12-31"),
    )


class TestQueueStatusChange:
    def test_writes_queue_entry_for_submit(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            # Set admin recipients
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), "2025-01-01T00:00:00Z"),
            )
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            entity = {"requester_id": "U1"}
            current_user = {"user_id": "U1", "role": "requester", "machine_id": "M1"}
            notification_service.queue_status_change(conn, "sc", "SC1", "submit", entity, current_user)
            conn.commit()

        with connect(app_config) as conn:
            rows = conn.execute("SELECT * FROM notification_queue").fetchall()
            assert len(rows) == 1
            row = dict(rows[0])
            assert row["entity_type"] == "sc"
            assert row["entity_id"] == "SC1"
            assert row["event_type"] == "status_change"
            assert row["event_key"] == "submit"
            assert row["status"] == "pending"
            to_ids = json.loads(row["to_recipients"])
            assert "U2" in to_ids  # admin recipient
            cc_ids = json.loads(row["cc_recipients"])
            assert "U1" in cc_ids  # requester

    def test_queue_write_uses_actor_keyword(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), "2025-01-01T00:00:00Z"),
            )
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            entity = {"requester_id": "U1"}
            current_user = {"user_id": "U2", "role": "admin", "machine_id": "M2"}
            notification_service.queue_status_change(conn, "sc", "SC1", "approve", entity, current_user)
            conn.commit()

        with connect(app_config) as conn:
            row = dict(conn.execute("SELECT * FROM notification_queue").fetchone())
            to_ids = json.loads(row["to_recipients"])
            cc_ids = json.loads(row["cc_recipients"])
            assert "U1" in to_ids  # requester is primary
            assert "U2" in cc_ids  # actor (admin) is CC

    def test_skips_when_no_rules_configured(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            entity = {"requester_id": "U1"}
            current_user = {"user_id": "U1", "role": "requester", "machine_id": "M1"}
            notification_service.queue_status_change(conn, "gr", "GR1", "approve", entity, current_user)
            conn.commit()

        with connect(app_config) as conn:
            rows = conn.execute("SELECT * FROM notification_queue").fetchall()
            assert len(rows) == 0  # No transition rules = nothing queued

    def test_skips_when_no_to_recipients(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            # admin_recipients is empty, and submit rules point to admin_recipients
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", "[]", "2025-01-01T00:00:00Z"),
            )
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            entity = {"requester_id": "U1"}
            current_user = {"user_id": "U1", "role": "requester", "machine_id": "M1"}
            # submit rule has to:["notify.admin_recipients"] which resolves to empty
            notification_service.queue_status_change(conn, "sc", "SC1", "submit", entity, current_user)
            conn.commit()

        with connect(app_config) as conn:
            rows = conn.execute("SELECT * FROM notification_queue").fetchall()
            assert len(rows) == 0

    def test_merges_per_sc_cc_list(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            _seed_user(conn, "U3", "M3", "requester")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), "2025-01-01T00:00:00Z"),
            )
            conn.execute(
                "INSERT INTO notification_config (entity_type, entity_id, enabled, cc_user_ids) VALUES ('sc', 'SC1', 1, ?)",
                (json.dumps(["U3"]),),
            )
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            entity = {"requester_id": "U1"}
            current_user = {"user_id": "U1", "role": "requester", "machine_id": "M1"}
            notification_service.queue_status_change(conn, "sc", "SC1", "submit", entity, current_user)
            conn.commit()

        with connect(app_config) as conn:
            row = dict(conn.execute("SELECT * FROM notification_queue").fetchone())
            cc_ids = json.loads(row["cc_recipients"])
            assert "U3" in cc_ids  # From per-SC config


class TestScNotificationConfig:
    def test_save_and_get(self, app_config):
        migrate(app_config)
        data = {
            "enabled": True,
            "cc_user_ids": ["U2", "U3"],
            "date_thresholds": [6, 3],
            "amount_thresholds": [50, 10],
        }
        notification_service.save_sc_notification_config(app_config, "SC1", data)
        result = notification_service.get_sc_notification_config(app_config, "SC1")
        assert result == data

    def test_returns_none_for_unconfigured_sc(self, app_config):
        migrate(app_config)
        result = notification_service.get_sc_notification_config(app_config, "SC_NONE")
        assert result is None

    def test_save_updates_existing(self, app_config):
        migrate(app_config)
        notification_service.save_sc_notification_config(app_config, "SC1", {"enabled": True, "cc_user_ids": [], "date_thresholds": [6], "amount_thresholds": [50]})
        notification_service.save_sc_notification_config(app_config, "SC1", {"enabled": False, "cc_user_ids": ["U1"], "date_thresholds": [3], "amount_thresholds": [30]})
        result = notification_service.get_sc_notification_config(app_config, "SC1")
        assert result["enabled"] is False
        assert result["cc_user_ids"] == ["U1"]


class TestNotificationDefaults:
    def test_save_and_get(self, app_config):
        migrate(app_config)
        data = {
            "admin_recipients": ["U2"],
            "transitions": {
                "sc": {"submit": {"to": ["notify.admin_recipients"], "cc": ["requester"]}},
                "po": {"create": {"to": ["notify.admin_recipients"], "cc": []}},
                "gr": {"create": {"to": ["notify.admin_recipients"], "cc": []}},
            },
            "default_cc": ["U3"],
            "date_thresholds": [6, 3, 1],
            "amount_thresholds": [50, 30],
        }
        notification_service.save_notification_defaults(app_config, data)
        result = notification_service.get_notification_defaults(app_config)
        assert result["notify.admin_recipients"] == ["U2"]
        assert result["notify.default_cc"] == ["U3"]
        assert result["notify.default_date_thresholds"] == [6, 3, 1]
        assert result["notify.default_amount_thresholds"] == [50, 30]


class TestListNotificationQueue:
    def test_list_with_filters(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), "2025-01-01T00:00:00Z"),
            )
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            entity = {"requester_id": "U1"}
            current_user = {"user_id": "U1", "role": "requester", "machine_id": "M1"}
            notification_service.queue_status_change(conn, "sc", "SC1", "submit", entity, current_user)
            notification_service.queue_status_change(conn, "sc", "SC1", "submit", entity, current_user)  # dup - ignored
            notification_service.queue_status_change(conn, "sc", "SC2", "submit", entity, current_user)
            conn.commit()

        result = notification_service.list_notification_queue(app_config)
        assert result["total"] == 2

        result = notification_service.list_notification_queue(app_config, sc_id="SC1")
        assert result["total"] == 1
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/test_notification_service.py -v`
Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_notification_service.py
git commit -m "test: add notification_service tests — queue writer and config CRUD"
```

---

### Task 13: Tests — Threshold Logic

**Files:**
- Create: `tests/test_notification_thresholds.py`

- [ ] **Step 1: Create test_notification_thresholds.py**

```python
"""Tests for daily threshold check logic."""

import json
from datetime import date, timedelta

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.notification import thresholds


def _seed_user(conn, user_id, machine_id, role="requester", email=None):
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, machine_id, user_name, role, email, status) VALUES (?, ?, ?, ?, ?, 'active')",
        (user_id, machine_id, f"User {user_id}", role, email or f"{user_id}@test.com"),
    )


def _seed_sc(conn, sc_id, requester_id, status="approved", sc_amount=100000, service_period_end=None):
    conn.execute(
        """INSERT OR REPLACE INTO sc_records (sc_id, requester_id, status, request_type, cost_center,
           sc_amount, service_period_start, service_period_end, description, created_at, updated_at)
           VALUES (?, ?, ?, 'material', 'CC1', ?, '2025-01-01', ?, '', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')""",
        (sc_id, requester_id, status, sc_amount, service_period_end or "2026-12-31"),
    )


class TestDateThresholds:
    def test_fires_when_below_threshold(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), "2025-01-01T00:00:00Z"),
            )
            # End date is 5 months from now — should trigger 6m threshold
            end_date = date.today() + timedelta(days=150)
            _seed_sc(conn, "SC1", "U1", sc_amount=100000, service_period_end=end_date.isoformat())
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            date_count, amount_count = thresholds.check_all_active_scs(conn)
            conn.commit()
            assert date_count == 1  # 5 months < 6 months threshold
            assert amount_count == 0

            # Verify sent_threshold recorded
            sent = conn.execute(
                "SELECT * FROM notification_sent_threshold WHERE entity_id = 'SC1' AND event_key = 'threshold_date:6m'"
            ).fetchone()
            assert sent is not None

            # Verify queue entry
            queue_row = conn.execute(
                "SELECT * FROM notification_queue WHERE entity_id = 'SC1' AND event_key = 'threshold_date:6m'"
            ).fetchone()
            assert queue_row is not None

    def test_skips_when_above_threshold(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), "2025-01-01T00:00:00Z"),
            )
            # End date is 12 months from now
            end_date = date.today() + timedelta(days=365)
            _seed_sc(conn, "SC1", "U1", sc_amount=100000, service_period_end=end_date.isoformat())
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            date_count, amount_count = thresholds.check_all_active_scs(conn)
            conn.commit()
            assert date_count == 0

    def test_does_not_fire_twice(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), "2025-01-01T00:00:00Z"),
            )
            end_date = date.today() + timedelta(days=150)
            _seed_sc(conn, "SC1", "U1", sc_amount=100000, service_period_end=end_date.isoformat())
            # Pre-record that 6m threshold was already sent
            conn.execute(
                "INSERT INTO notification_sent_threshold (entity_type, entity_id, event_key, sent_at) VALUES ('sc', 'SC1', 'threshold_date:6m', '2025-01-01T00:00:00Z')"
            )
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            date_count, _ = thresholds.check_all_active_scs(conn)
            conn.commit()
            assert date_count == 0  # Already sent, skip


class TestAmountThresholds:
    def test_fires_when_below_threshold(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), "2025-01-01T00:00:00Z"),
            )
            _seed_sc(conn, "SC1", "U1", sc_amount=100000)
            # Create approved GR consuming 80% of SC amount
            conn.execute(
                """INSERT INTO gr_requests (gr_id, sc_id, po_id, vendor_id, gr_no, con_value, estimated_amount,
                   status, created_at, updated_at)
                   VALUES ('GR1', 'SC1', 'PO1', 'V1', 'GR001', 80000, 80000, 'approved',
                   '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')"""
            )
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _, amount_count = thresholds.check_all_active_scs(conn)
            conn.commit()
            assert amount_count == 1  # 20% remaining < 50%, 30% thresholds — fires tightest

            sent = conn.execute(
                "SELECT event_key FROM notification_sent_threshold WHERE entity_id = 'SC1' AND event_key LIKE 'threshold_amount:%'"
            ).fetchone()
            assert sent is not None
            # Should fire 30% (tightest threshold below 20%)
            assert sent["event_key"] == "threshold_amount:30%"

    def test_skips_when_above_threshold(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), "2025-01-01T00:00:00Z"),
            )
            _seed_sc(conn, "SC1", "U1", sc_amount=100000)
            # 60% remaining — above all thresholds (50%, 30%, 10%)
            conn.execute(
                """INSERT INTO gr_requests (gr_id, sc_id, po_id, vendor_id, gr_no, con_value, estimated_amount,
                   status, created_at, updated_at)
                   VALUES ('GR1', 'SC1', 'PO1', 'V1', 'GR001', 40000, 40000, 'approved',
                   '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')"""
            )
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _, amount_count = thresholds.check_all_active_scs(conn)
            conn.commit()
            assert amount_count == 0


class TestDisabledConfig:
    def test_skips_when_disabled(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), "2025-01-01T00:00:00Z"),
            )
            end_date = date.today() + timedelta(days=150)
            _seed_sc(conn, "SC1", "U1", sc_amount=100000, service_period_end=end_date.isoformat())
            conn.execute(
                "INSERT INTO notification_config (entity_type, entity_id, enabled) VALUES ('sc', 'SC1', 0)"
            )
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            date_count, amount_count = thresholds.check_all_active_scs(conn)
            conn.commit()
            assert date_count == 0
            assert amount_count == 0
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/test_notification_thresholds.py -v`
Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_notification_thresholds.py
git commit -m "test: add threshold check logic tests"
```

---

### Task 14: Tests — Bridge Endpoints

**Files:**
- Create: `tests/test_notification_bridge.py`

- [ ] **Step 1: Create test_notification_bridge.py**

```python
"""Tests for notification API bridge endpoints."""

import json

from sc_gr_app.api import bridge
from sc_gr_app.db.migrations import migrate


def _seed_user(conn, user_id, machine_id, role="requester", email=None):
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, machine_id, user_name, role, email, status) VALUES (?, ?, ?, ?, ?, 'active')",
        (user_id, machine_id, f"User {user_id}", role, email or f"{user_id}@test.com"),
    )


class TestBridgeNotificationEndpoints:
    def test_get_sc_notification_config(self, monkeypatch, app_config):
        migrate(app_config)
        from sc_gr_app.db.connection import connect
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "1234567", "requester")
            conn.execute(
                "INSERT INTO notification_config (entity_type, entity_id, enabled, cc_user_ids) VALUES ('sc', 'SC1', 1, '[\"U2\"]')"
            )
            conn.commit()

        monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
        monkeypatch.setattr(bridge, "get_user_by_machine_id",
                            lambda config, machine_id: {"user_id": "U1", "role": "requester", "machine_id": "1234567"})

        api = bridge.ApiBridge(app_config)
        result = api.get_sc_notification_config({"sc_id": "SC1"})
        assert result["ok"] is True
        assert result["data"]["enabled"] is True
        assert result["data"]["cc_user_ids"] == ["U2"]

    def test_get_sc_notification_config_returns_none_for_unconfigured(self, monkeypatch, app_config):
        migrate(app_config)
        from sc_gr_app.db.connection import connect
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "1234567", "requester")
            conn.commit()

        monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
        monkeypatch.setattr(bridge, "get_user_by_machine_id",
                            lambda config, machine_id: {"user_id": "U1", "role": "requester", "machine_id": "1234567"})

        api = bridge.ApiBridge(app_config)
        result = api.get_sc_notification_config({"sc_id": "SC_NONE"})
        assert result["ok"] is True
        assert result["data"] is None

    def test_save_sc_notification_config(self, monkeypatch, app_config):
        migrate(app_config)
        from sc_gr_app.db.connection import connect
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "1234567", "requester")
            conn.commit()

        monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
        monkeypatch.setattr(bridge, "get_user_by_machine_id",
                            lambda config, machine_id: {"user_id": "U1", "role": "requester", "machine_id": "1234567"})

        api = bridge.ApiBridge(app_config)
        result = api.save_sc_notification_config({
            "sc_id": "SC1",
            "data": {"enabled": True, "cc_user_ids": ["U2"], "date_thresholds": [6], "amount_thresholds": [50]}
        })
        assert result["ok"] is True

        # Verify it was saved
        verify = api.get_sc_notification_config({"sc_id": "SC1"})
        assert verify["data"]["date_thresholds"] == [6]

    def test_get_notification_defaults_admin_only(self, monkeypatch, app_config):
        migrate(app_config)
        from sc_gr_app.db.connection import connect
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "1234567", "admin")
            conn.commit()

        monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
        monkeypatch.setattr(bridge, "get_user_by_machine_id",
                            lambda config, machine_id: {"user_id": "U1", "role": "admin", "machine_id": "1234567"})

        api = bridge.ApiBridge(app_config)
        result = api.get_notification_defaults()
        assert result["ok"] is True
        assert "notify.admin_recipients" in result["data"]

    def test_list_notification_queue(self, monkeypatch, app_config):
        migrate(app_config)
        from sc_gr_app.db.connection import connect
        from sc_gr_app.services import notification_service

        with connect(app_config) as conn:
            _seed_user(conn, "U1", "1234567", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), "2025-01-01T00:00:00Z"),
            )
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            notification_service.queue_status_change(
                conn, "sc", "SC1", "submit",
                {"requester_id": "U1"},
                {"user_id": "U1", "role": "requester", "machine_id": "1234567"},
            )
            conn.commit()

        monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
        monkeypatch.setattr(bridge, "get_user_by_machine_id",
                            lambda config, machine_id: {"user_id": "U1", "role": "requester", "machine_id": "1234567"})

        api = bridge.ApiBridge(app_config)
        result = api.list_notification_queue({"sc_id": "SC1"})
        assert result["ok"] is True
        assert result["data"]["total"] == 1
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_notification_bridge.py -v`
Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_notification_bridge.py
git commit -m "test: add notification bridge endpoint tests"
```

---

### Task 15: Verify Existing Tests Still Pass

**Files:**
- Run: `uv run pytest -q`

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -q`
Expected: All existing tests pass. No regressions from the notification integration.

If any test fails because test databases don't have v3 migration tables, fix by adding `migrate(app_config)` call to the failing test's setup. The notification service integration in SC/PO/GR services is safe because `queue_status_change` returns early when no transition rules are configured (test DBs don't have `notify.transitions.*` settings).

- [ ] **Step 2: Commit any fixes needed**

```bash
git add -A
git commit -m "fix: ensure existing tests pass with notification integration"
```

---

### Task 16: Final Integration Verification

- [ ] **Step 1: Start the desktop app and verify UI**

Run: `uv run python -m sc_gr_app.main` (dev mode)
- Navigate to an SC detail page → verify "Notification Settings" card appears
- Navigate to System Settings → verify "Notification Defaults" card appears (admin only)
- Submit an SC → verify a row appears in `notification_queue` table
- Save notification config → verify `notification_config` table updated

- [ ] **Step 2: Test the notification script (dry run)**

Run: `uv run python -m sc_gr_app.notification --run-once`
Expected: Script starts, connects to DB, processes any pending queue entries, runs threshold check, exits.

- [ ] **Step 3: Run full test suite one final time**

Run: `uv run pytest -q`
Expected: All tests pass.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete email notification system"
```
