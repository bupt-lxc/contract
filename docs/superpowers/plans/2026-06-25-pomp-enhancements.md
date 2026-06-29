# POMP Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement ~13 enhancements across schema changes, import/export for SC/PO/GR, user self-registration, email overhaul, and UI/localization improvements.

**Architecture:** Changes span all layers — Python services/API bridge (backend), Vue 3 frontend, and packaging scripts. Tasks are grouped by dependency: schema changes first, then backend services, then frontend. Streams B (import), C (registration), D (email), and E (UI) can be worked on in parallel once Stream A (schema) is done.

**Tech Stack:** Python 3.11, SQLite, pywebview, Vue 3 + Element Plus + vue-i18n, win32com (Outlook), Inno Setup, PowerShell

---

### Task 1: SC currency field (A1)

**Files:**
- Modify: `sc_gr_app/db/migrations.py` (add v26 migration)
- Modify: `sc_gr_app/services/sc_service.py` (create_sc_draft, submit_sc — accept currency)
- Modify: `sc_gr_app/services/query_service.py` (return currency in search results)
- Modify: `sc_gr_app/api/bridge.py` (pass currency through in SC bridge methods)
- Modify: `frontend/src/components/sc/ScFormDialog.vue` (currency dropdown)
- Modify: `frontend/src/i18n/locales/en-US.js` (add currency labels)
- Modify: `frontend/src/i18n/locales/zh-CN.js` (add currency labels)

- [ ] **Step 1: Add migration v26 in `sc_gr_app/db/migrations.py`**

Increment `SCHEMA_VERSION` from 25 to 26. Add `_migrate_v26` function and register it in `migrate()`:

```python
SCHEMA_VERSION = 26

# ... (after existing migrations)

def _migrate_v26(conn) -> None:
    """Add currency column to sc_records."""
    if _table_exists(conn, "sc_records"):
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(sc_records)")}
        if "currency" not in existing:
            conn.execute("ALTER TABLE sc_records ADD COLUMN currency TEXT NOT NULL DEFAULT 'CNY'")
    _record(conn, 26)
```

In `migrate()`, add after the v25 block:

```python
if 26 not in _applied_versions(conn):
    conn.execute("BEGIN")
    _migrate_v26(conn)
    conn.commit()
```

- [ ] **Step 2: Update `sc_service.py` — add currency to INSERT, UPDATE, and OPTIONAL_UPDATE_FIELDS**

At line 28-42, add `"currency"` to `OPTIONAL_UPDATE_FIELDS`:

```python
OPTIONAL_UPDATE_FIELDS = (
    "sc_no",
    "request_type",
    "cost_center",
    "sc_amount",
    "service_period_start",
    "service_period_end",
    "description",
    "asset",
    "asset_nums",
    "internal_system_number",
    "currency",
    "vendor_ids",
)
```

In `create_sc_draft` (line 510), add `currency` to the INSERT column list and values tuple. The INSERT currently has 21 columns; add `currency` as column 22:

```python
# INSERT column list — add currency after internal_system_number
"""
insert into sc_records (
  sc_id, sc_no, requester_id, request_type, cost_center,
  sc_amount, service_period_start, service_period_end,
  status, description, created_by, created_at, updated_at,
  approved_by, approved_at, closed_at, asset, asset_nums,
  pending_date, approved_date, internal_system_number,
  currency
) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

# Values tuple — add currency as last value
(
    sc_id, data.get("sc_no"), data["requester_id"],
    data.get("request_type"), data.get("cost_center"),
    float(data["sc_amount"]) if data.get("sc_amount") not in (None, "") else None,
    data.get("service_period_start"), data.get("service_period_end"),
    "draft", data.get("description"), current_user["user_id"],
    timestamp, timestamp, None, None, None,
    data.get("asset", "N"), data.get("asset_nums"),
    None, None, data.get("internal_system_number"),
    data.get("currency", "CNY"),
)
```

In `submit_sc` (line 625), add `currency` to the UPDATE statement. After `internal_system_number = ?,` add:

```python
update sc_records
set sc_no = ?,
    request_type = ?,
    cost_center = ?,
    sc_amount = ?,
    service_period_start = ?,
    service_period_end = ?,
    description = ?,
    asset = ?,
    asset_nums = ?,
    currency = ?,
    internal_system_number = ?,
    status = 'manager_confirm',
    updated_at = ?
where sc_id = ?
```

And add `merged.get("currency", "CNY")` to the corresponding values tuple at the right position.

Also in the `update_sc` function (line 734), `currency` will now flow through `OPTIONAL_UPDATE_FIELDS` automatically — no code change needed there since it already filters by `allowed`.

- [ ] **Step 3: Update `query_service.py` — include currency in SC search**

The `_search` function already does `SELECT *` so currency will be included automatically for SC queries. Verify by running:

```bash
uv run pytest tests/ -q -k "search_sc"
```

- [ ] **Step 4: Update bridge.py — pass currency through SC endpoints**

In the SC-related bridge methods (`create_sc_draft`, `submit_sc`, `get_sc_detail`, etc.), ensure `currency` is included in output data. For `get_sc_detail`, currency will come through automatically from the SELECT query. For create/submit, make sure it's passed through from the payload.

- [ ] **Step 5: Add currency dropdown to `ScFormDialog.vue`**

Add a new form item in the SC form, near the top section (before or after sc_amount):

```vue
<el-form-item :label="$t('sc.currency')" prop="currency">
  <el-select v-model="form.currency" :placeholder="$t('sc.currency')">
    <el-option label="¥ CNY" value="CNY" />
    <el-option label="€ EUR" value="EUR" />
    <el-option label="$ USD" value="USD" />
  </el-select>
</el-form-item>
```

Default `form.currency` to `'CNY'` in the form data initialization.

- [ ] **Step 6: Add i18n keys**

In `en-US.js`, add:
```js
sc: {
  // ... existing
  currency: 'Currency',
}
```

In `zh-CN.js`, add:
```js
sc: {
  // ... existing
  currency: '货币',
}
```

- [ ] **Step 7: Run tests and commit**

```bash
uv run pytest -q
git add sc_gr_app/db/migrations.py sc_gr_app/services/sc_service.py sc_gr_app/services/query_service.py sc_gr_app/api/bridge.py frontend/src/components/sc/ScFormDialog.vue frontend/src/i18n/locales/en-US.js frontend/src/i18n/locales/zh-CN.js
git commit -m "feat: add currency field to SC (CNY/EUR/USD), default CNY"
```

---

### Task 2: Vendor ID auto-generation (A3)

**Files:**
- Modify: `sc_gr_app/services/vendor_service.py` (auto-generate vendor_id)
- Modify: `sc_gr_app/api/bridge.py` (remove vendor_id requirement from create payload)
- Modify: `frontend/src/components/vendor/VendorFormDialog.vue` (remove vendor ID input, add full-name hint)

- [ ] **Step 1: Update `create_vendor` in `vendor_service.py`**

Change `REQUIRED_FIELDS` to remove `vendor_id`:

```python
REQUIRED_FIELDS = ("vendor_name", "service_scope")
```

In `create_vendor`, auto-generate `vendor_id`:

```python
def create_vendor(config: AppConfig, current_user: dict, data: dict) -> dict:
    require_requester_or_admin(current_user)
    _require_fields(data, REQUIRED_FIELDS)
    if data["service_scope"] not in SUPPORTED_SERVICE_SCOPES:
        raise ValidationError("service_scope is invalid")

    timestamp = utc_now()

    with LeaseLock(config.lock_dir, "system", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                # Auto-generate vendor_id: V + 6-digit sequence
                row = conn.execute(
                    "SELECT COALESCE(MAX(CAST(SUBSTR(vendor_id, 2) AS INTEGER)), 0) + 1 AS next_id FROM vendors"
                ).fetchone()
                vendor_id = f"V{row['next_id']:06d}"

                conn.execute(
                    """INSERT INTO vendors (...)""",
                    (vendor_id, ...)
                )
                # ... rest unchanged
```

- [ ] **Step 2: Update `vendor_service.py` — import also uses auto-ID**

In `import_vendors` (or similar function), remove the requirement for vendor_id in input rows. Generate a new vendor_id for each imported row similarly.

- [ ] **Step 3: Update bridge.py — vendor create endpoint**

Find `create_vendor` bridge method. It passes payload to `vendor_service.create_vendor`. No change needed in the bridge itself since vendor_id is no longer required from the client. Verify the bridge method still works.

- [ ] **Step 4: Update `VendorFormDialog.vue`**

Remove the vendor_id input field from the create form. In edit mode, show vendor_id as read-only. Add "(Full Name Required)" hint to vendor_name label:

```vue
<el-form-item label="Vendor Name (Full Name Required)" prop="vendor_name">
  <el-input v-model="form.vendor_name" />
</el-form-item>
```

Remove vendor_id from form data initialization and validation rules for create mode.

- [ ] **Step 5: Update i18n keys for vendor form**

In `en-US.js`:
```js
vendor: {
  // ... existing
  vendorNameFull: 'Vendor Name (Full Name Required)',
  vendorId: 'Vendor ID',
}
```

In `zh-CN.js`:
```js
vendor: {
  // ... existing
  vendorNameFull: '供应商名称（需全称）',
  vendorId: '供应商ID',
}
```

- [ ] **Step 6: Run tests and commit**

```bash
uv run pytest tests/test_vendor_service.py -q
git add sc_gr_app/services/vendor_service.py sc_gr_app/api/bridge.py frontend/src/components/vendor/VendorFormDialog.vue frontend/src/i18n/locales/en-US.js frontend/src/i18n/locales/zh-CN.js
git commit -m "feat: auto-generate vendor_id (V+6-digit), add full-name label hint"
```

---

### Task 3: Audit → Record rename (A4)

**Files:**
- Modify: `sc_gr_app/db/migrations.py` (v27: rename table)
- Modify: `sc_gr_app/services/audit_service.py` → rename to `record_service.py`, rename functions
- Modify: `sc_gr_app/services/vendor_service.py` (update import)
- Modify: `sc_gr_app/services/sc_service.py` (update import)
- Modify: `sc_gr_app/services/po_service.py` (update import)
- Modify: `sc_gr_app/services/gr_service.py` (update import)
- Modify: `sc_gr_app/api/bridge.py` (update import, rename bridge methods)
- Modify: `frontend/src/i18n/locales/en-US.js`
- Modify: `frontend/src/i18n/locales/zh-CN.js`
- Modify: `frontend/src/views/LogsView.vue` (if it exists; check router)
- Modify: `frontend/src/router/index.js` (route name)
- Modify: `frontend/src/composables/useLogs.js` (API method name)

- [ ] **Step 1: Add migration v27 to rename audit_logs table**

In `migrations.py`, add:

```python
def _migrate_v27(conn) -> None:
    """Rename audit_logs to operation_records."""
    if _table_exists(conn, "audit_logs") and not _table_exists(conn, "operation_records"):
        conn.execute("ALTER TABLE audit_logs RENAME TO operation_records")
    _record(conn, 27)
```

Register in `migrate()`.

- [ ] **Step 2: Rename `audit_service.py` → `record_service.py`**

Create the new file with renamed functions:

```python
# sc_gr_app/services/record_service.py
import json
from datetime import datetime, timezone
from uuid import uuid4

_SKIP_DIFF_FIELDS = {
    "created_at", "updated_at", "created_by",
    "approved_by", "approved_at", "closed_at",
    "cancelled_by", "cancelled_at",
}

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

# ... (same _diff_changes and _fmt_val as before)

def write_operation_record(
    conn, *, action_type, object_type, object_id, sc_id,
    operator_id, machine_id, before, after, operation_mode="normal",
) -> None:
    changes_summary = _diff_changes(before, after)
    conn.execute(
        """
        INSERT INTO operation_records (
          log_id, action_type, object_type, object_id, sc_id,
          operator_id, machine_id, before_json, after_json,
          changes_summary, operation_mode, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (str(uuid4()), action_type, object_type, object_id, sc_id,
         operator_id, machine_id,
         json.dumps(before, ensure_ascii=False) if before else None,
         json.dumps(after, ensure_ascii=False) if after else None,
         changes_summary, operation_mode, utc_now()),
    )
```

- [ ] **Step 3: Update all imports across the codebase**

In every file that imports from `audit_service`, update:

```python
# Old
from sc_gr_app.services.audit_service import write_audit_log
# New
from sc_gr_app.services.record_service import write_operation_record
```

And update all call sites from `write_audit_log(...)` to `write_operation_record(...)`.

Files to update:
- `sc_gr_app/services/vendor_service.py:10,114,182,215,253`
- `sc_gr_app/services/sc_service.py` (all calls)
- `sc_gr_app/services/po_service.py` (all calls)
- `sc_gr_app/services/gr_service.py` (all calls)
- `sc_gr_app/api/bridge.py:9` (import and all calls)

- [ ] **Step 4: Update bridge.py — rename search method**

```python
# Old
def search_audit_logs(self, payload) -> dict:
    # ...
    result = query_service.search_audit_logs(self.config, ...)
# New
def search_operation_records(self, payload) -> dict:
    # ...
    result = query_service.search_operation_records(self.config, ...)
```

Also update `query_service.py` — rename `search_audit_logs` to `search_operation_records` and update ALL internal SQL references to `operation_records` table:

In `query_service.py` lines 713-785+, replace every occurrence of `audit_logs` with `operation_records` in SQL strings. This includes:
- Line 729: `audit_logs.sc_id` → `operation_records.sc_id`
- Line 732-733: `sc.sc_id = audit_logs.sc_id` → `sc.sc_id = operation_records.sc_id`
- Line 747: `audit_logs.sc_id` / `audit_logs.operator_id` → `operation_records.sc_id` / `operation_records.operator_id`
- Line 751-752: `sc.sc_id = audit_logs.sc_id` → `sc.sc_id = operation_records.sc_id`
- Line 763: `select * from audit_logs` → `select * from operation_records`

Also rename the indexes for consistency (optional but recommended):

```python
# In migration v27, also recreate indexes with new names:
conn.execute("DROP INDEX IF EXISTS idx_audit_sc")
conn.execute("DROP INDEX IF EXISTS idx_audit_created")
conn.execute("CREATE INDEX IF NOT EXISTS idx_operation_records_sc ON operation_records(sc_id)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_operation_records_created ON operation_records(created_at)")
```

- [ ] **Step 5: Update frontend i18n keys**

In `en-US.js`:
```js
record: {
  operationRecord: 'Operation Record',
  // ... any other audit keys become record keys
}
```

In `zh-CN.js`:
```js
record: {
  operationRecord: '操作记录',
  // ...
}
```

- [ ] **Step 6: Update frontend JS — rename API method calls**

In `useLogs.js`:
```js
// Old
const result = await callApi('search_audit_logs', params)
// New
const result = await callApi('search_operation_records', params)
```

- [ ] **Step 7: Update `LogsView.vue` — labels**

Change all "Audit Log" / "审计日志" references to "Operation Record" / "操作记录". Update page title and any column headers.

- [ ] **Step 8: Update router**

In `router/index.js`, if there's a route named "audit" or "logs", ensure it uses the new naming.

- [ ] **Step 9: Run tests and commit**

```bash
uv run pytest -q
git add .
git commit -m "refactor: rename audit_logs to operation_records across all layers"
```

---

### Task 4: Log time format (A5)

**Files:**
- Modify: `sc_gr_app/services/record_service.py` (format timestamps)
- Modify: `sc_gr_app/services/query_service.py` (format timestamps in search results)

- [ ] **Step 1: Create a shared time formatter**

In `record_service.py`, update `utc_now` or add a display formatter:

```python
def format_timestamp(iso_str: str) -> str:
    """Convert ISO UTC timestamp to display format: YYYY-MM-DD HH:MM:SS"""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return iso_str
```

- [ ] **Step 2: Apply formatter in query_service.py**

In the `_search` function, for operation records results, format `created_at` before returning. Or, more broadly, in the bridge methods that return timestamps to the frontend, apply the formatter.

Add a helper in bridge.py or schemas.py:

```python
def _format_entity_timestamps(entity: dict, fields=("created_at", "updated_at", "pending_date", "approved_date", "closed_at", "cancelled_at", "confirmed_at")) -> dict:
    for f in fields:
        if f in entity and entity[f]:
            entity[f] = format_timestamp(entity[f])
    return entity
```

Apply this to all entity responses from the bridge.

- [ ] **Step 3: Verify and commit**

```bash
uv run pytest -q
git add sc_gr_app/services/record_service.py sc_gr_app/services/query_service.py sc_gr_app/api/bridge.py
git commit -m "fix: format timestamps as YYYY-MM-DD HH:MM:SS in UI"
```

---

### Task 5: SC allow no vendor + bilingual prompt (A2 + E6)

**Files:**
- Modify: `sc_gr_app/db/migrations.py` (ensure vendor_id nullable on sc_records, check sc_vendors)
- Modify: `frontend/src/components/sc/ScFormDialog.vue` (make vendor optional, add prompt)
- Modify: `frontend/src/components/sc/ScVendorSection.vue` (make vendor field optional)

- [ ] **Step 1: Verify schema allows NULL vendor on SC**

Check that `sc_records` doesn't have a vendor_id column directly — it uses the `sc_vendors` junction table (v14 migration). So "SC allow no vendor" means the SC can have zero rows in `sc_vendors`. The schema already supports this since `sc_vendors` is a junction table. No migration needed.

- [ ] **Step 2: Update SC form — make vendor optional AND remove server-side vendor requirement**

In `ScFormDialog.vue` and/or `ScVendorSection.vue`, remove any `required` validation on the vendor field. The user can now submit an SC without selecting a vendor.

In `sc_gr_app/services/sc_service.py`, `submit_sc` at line 658-663 currently requires at least one vendor:

```python
# REMOVE these lines (658-663 in submit_sc):
vendor_count = conn.execute(
    "SELECT COUNT(*) as cnt FROM sc_vendors WHERE sc_id = ?", (sc_id,)
).fetchone()["cnt"]
if vendor_count == 0:
    raise ValidationError("At least one vendor is required to submit the SC")
```

Delete this validation block entirely — SCs can now be submitted without any vendor.

- [ ] **Step 3: Add bilingual vendor prompt**

Add an info box near the vendor section in the SC form, visible in both create and edit modes:

```vue
<el-alert type="info" :closable="false" show-icon>
  <template #title>
    <div>
      <p style="margin:0 0 8px 0;line-height:1.6">
        中文：如果需要采购遴选供应商，可在PO生成后再补充供应商信息。如不需要采购审核，需要填写经比价确定或唯一指定的供应商信息（请将比价证明或唯一指定证明材料作为附件上传）
      </p>
      <p style="margin:0;line-height:1.6;color:#64748b">
        English: If procurement vendor selection is required, vendor information can be supplemented after PO creation. If procurement review is not required, please provide vendor information determined through price comparison or sole-source designation (please upload price comparison proof or sole-source designation documents as attachments)
      </p>
    </div>
  </template>
</el-alert>
```

This should be always visible regardless of system language.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/sc/ScFormDialog.vue frontend/src/components/sc/ScVendorSection.vue
git commit -m "feat: make SC vendor optional, add bilingual vendor selection prompt"
```

---

### Task 6: SC import (B1+B2 — SC)

**Files:**
- Create: `sc_gr_app/services/import_service.py`
- Modify: `sc_gr_app/api/bridge.py` (add import_scs, download_sc_template)
- Modify: `frontend/src/views/ScListView.vue` (add import/template buttons)
- Modify: `frontend/src/i18n/locales/en-US.js`
- Modify: `frontend/src/i18n/locales/zh-CN.js`

- [ ] **Step 1: Create `import_service.py`**

```python
"""Bulk import service for SC, PO, GR records with direct status writes."""
from datetime import datetime, timezone
from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ValidationError
from sc_gr_app.services.record_service import write_operation_record
from sc_gr_app.services.lock_service import LeaseLock

SC_IMPORT_FIELDS = [
    "sc_id", "sc_no", "requester_id", "request_type", "cost_center",
    "sc_amount", "service_period_start", "service_period_end", "status",
    "description", "currency", "internal_system_number"
]

SC_ALLOWED_STATUSES = {"draft", "manager_confirm", "pending", "approved", "denied", "closed"}

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _validate_rows(conn, rows: list[dict], entity_type: str) -> list[dict]:
    """Validate all rows. Returns list of error dicts."""
    errors = []
    for i, row in enumerate(rows, start=1):
        # Check required fields
        for field in ["sc_id", "requester_id", "sc_amount", "status"]:
            if not row.get(field):
                errors.append({"row": i, "field": field, "message": f"{field} is required"})
        # Check status
        status = row.get("status", "")
        if status and status not in SC_ALLOWED_STATUSES:
            errors.append({"row": i, "field": "status", "message": f"Invalid status: {status}"})
        # Check requester exists
        if row.get("requester_id"):
            exists = conn.execute(
                "SELECT 1 FROM users WHERE user_id = ?", (row["requester_id"],)
            ).fetchone()
            if not exists:
                errors.append({"row": i, "field": "requester_id", "message": f"User {row['requester_id']} not found"})
        # Check SC ID uniqueness
        if row.get("sc_id"):
            exists = conn.execute(
                "SELECT 1 FROM sc_records WHERE sc_id = ?", (row["sc_id"],)
            ).fetchone()
            if exists:
                errors.append({"row": i, "field": "sc_id", "message": f"SC {row['sc_id']} already exists"})
    return errors

def import_scs(config: AppConfig, current_user: dict, rows: list[dict]) -> dict:
    """Import SC records with direct status writes."""
    timestamp = utc_now()
    with LeaseLock(config.lock_dir, "import:lock", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                errors = _validate_rows(conn, rows, "sc")
                if errors:
                    conn.rollback()
                    return {"ok": False, "errors": errors}

                imported = 0
                for row in rows:
                    conn.execute(
                        """INSERT INTO sc_records (
                          sc_id, sc_no, requester_id, request_type, cost_center,
                          sc_amount, service_period_start, service_period_end,
                          status, description, currency, internal_system_number,
                          created_by, created_at, updated_at, asset
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'N')""",
                        (
                            row["sc_id"], row.get("sc_no"), row["requester_id"],
                            row.get("request_type"), row.get("cost_center"),
                            row["sc_amount"], row.get("service_period_start"),
                            row.get("service_period_end"), row["status"],
                            row.get("description"), row.get("currency", "CNY"),
                            row.get("internal_system_number"),
                            current_user["user_id"], timestamp, timestamp,
                        ),
                    )
                    write_operation_record(
                        conn, action_type="import_sc", object_type="sc",
                        object_id=row["sc_id"], sc_id=row["sc_id"],
                        operator_id=current_user["user_id"],
                        machine_id=current_user["machine_id"],
                        before=None, after=dict(row),
                    )
                    imported += 1

                conn.commit()
                return {"ok": True, "count": imported}
            except Exception:
                conn.rollback()
                raise
```

- [ ] **Step 2: Add bridge endpoints**

In `bridge.py`:

```python
def import_scs(self, payload) -> dict:
    """Import SC records from Excel rows."""
    try:
        user = get_user_by_machine_id(self.config, get_7_digit_id())
        payload = self._required_payload(payload)
        rows = _require_payload_field(payload, "rows")
        result = import_service.import_scs(self.config, user, rows)
        if result.get("ok") is False:
            return fail(ValidationError(str(result.get("errors", []))))
        return ok(result)
    except PermissionDenied as e:
        return fail(e)
    except ValidationError as e:
        return fail(e)

def download_sc_template(self, _payload=None) -> dict:
    """Return SC import template as base64-encoded xlsx data."""
    import io
    import base64
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SC Import"
    headers = ["sc_id", "sc_no", "requester_id", "request_type", "cost_center",
               "sc_amount", "service_period_start", "service_period_end", "status",
               "description", "currency", "internal_system_number"]
    hints = ["Required", "Optional", "Required (user ID)", "material/service/fixed_asset/FC",
             "Cost center number", "Required (e.g. 50000)", "YYYY-MM-DD", "YYYY-MM-DD",
             "draft/pending/approved/closed/denied", "Optional", "CNY/EUR/USD", "Optional (FC only)"]
    for col, (h, hint) in enumerate(zip(headers, hints), start=1):
        ws.cell(row=1, column=col, value=h)
        ws.cell(row=2, column=col, value=hint)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("ascii")
    return ok({"filename": "SC_Import_Template.xlsx", "data": b64})
```

Also add `from sc_gr_app.services import import_service` at top.

- [ ] **Step 3: Add frontend import button and template download**

In `ScListView.vue`, add buttons similar to VendorListView pattern:

```vue
<el-button @click="importVisible = true">
  <el-icon><Upload /></el-icon> {{ $t('common.import') }}
</el-button>
<el-button @click="downloadTemplate">
  <el-icon><Download /></el-icon> {{ $t('common.downloadTemplate') }}
</el-button>
```

Add dialog and handler functions following the vendor import pattern. Use `useExport` composable's `exportRows` pattern for template download.

- [ ] **Step 4: Add i18n keys**

```js
// en-US.js
common: {
  import: 'Import',
  downloadTemplate: 'Download Template',
}
// zh-CN.js
common: {
  import: '导入',
  downloadTemplate: '下载模板',
}
```

- [ ] **Step 5: Run tests and commit**

```bash
uv run pytest -q
git add .
git commit -m "feat: add SC import with Excel template and direct status writes"
```

---

### Task 7: PO and GR import (B1+B2 — PO/GR)

**Files:**
- Modify: `sc_gr_app/services/import_service.py` (add import_pos, import_grs)
- Modify: `sc_gr_app/api/bridge.py` (add import_pos, import_grs, template endpoints)
- Modify: `frontend/src/views/PoListView.vue` (import buttons)
- Modify: `frontend/src/views/GrListView.vue` (import buttons)

- [ ] **Step 1: Add `import_pos` and `import_grs` to `import_service.py`**

```python
PO_IMPORT_FIELDS = [
    "po_id", "sc_id", "vendor_id", "po_no", "requester_id", "po_amount",
    "status", "contract_from", "contract_to", "contract_no",
    "payment_frequency", "contract_pos", "contract_type", "cost_center", "purchaser"
]

PO_ALLOWED_STATUSES = {"draft", "activing", "finished"}

def import_pos(config: AppConfig, current_user: dict, rows: list[dict]) -> dict:
    """Import PO records with direct status writes."""
    timestamp = utc_now()
    with LeaseLock(config.lock_dir, "import:lock", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                errors = []
                for i, row in enumerate(rows, start=1):
                    if not row.get("po_id"):
                        errors.append({"row": i, "field": "po_id", "message": "po_id is required"})
                    if not row.get("sc_id"):
                        errors.append({"row": i, "field": "sc_id", "message": "sc_id is required"})
                    elif not conn.execute("SELECT 1 FROM sc_records WHERE sc_id = ?", (row["sc_id"],)).fetchone():
                        errors.append({"row": i, "field": "sc_id", "message": f"SC {row['sc_id']} not found"})
                    if row.get("vendor_id"):
                        if not conn.execute("SELECT 1 FROM vendors WHERE vendor_id = ?", (row["vendor_id"],)).fetchone():
                            errors.append({"row": i, "field": "vendor_id", "message": f"Vendor {row['vendor_id']} not found"})
                    if row.get("status") and row["status"] not in PO_ALLOWED_STATUSES:
                        errors.append({"row": i, "field": "status", "message": f"Invalid status: {row['status']}"})
                if errors:
                    conn.rollback()
                    return {"ok": False, "errors": errors}

                imported = 0
                for row in rows:
                    conn.execute(
                        """INSERT INTO pos (po_id, sc_id, vendor_id, po_no, requester_id,
                          po_amount, status, contract_from, contract_to, contract_no,
                          payment_frequency, contract_pos, contract_type, cost_center,
                          purchaser, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (row["po_id"], row["sc_id"], row.get("vendor_id"), row.get("po_no"),
                         row.get("requester_id"), row["po_amount"], row.get("status", "draft"),
                         row.get("contract_from"), row.get("contract_to"), row.get("contract_no"),
                         row.get("payment_frequency"), row.get("contract_pos"),
                         row.get("contract_type"), row.get("cost_center"), row.get("purchaser"),
                         timestamp, timestamp),
                    )
                    write_operation_record(conn, action_type="import_po", object_type="po",
                        object_id=row["po_id"], sc_id=row["sc_id"],
                        operator_id=current_user["user_id"],
                        machine_id=current_user["machine_id"], before=None, after=dict(row))
                    imported += 1
                conn.commit()
                return {"ok": True, "count": imported}
            except Exception:
                conn.rollback()
                raise

GR_IMPORT_FIELDS = [
    "gr_id", "po_id", "gr_no", "requester_id", "estimated_amount", "con_value",
    "status", "remark", "tax_rate", "gross_cost", "goods_service_description",
    "confirmation_name", "delivery_from", "delivery_to", "last_delivery"
]

GR_ALLOWED_STATUSES = {"draft", "manager_confirm", "pending", "approved", "cancelled"}

def import_grs(config: AppConfig, current_user: dict, rows: list[dict]) -> dict:
    """Import GR records with direct status writes."""
    timestamp = utc_now()
    with LeaseLock(config.lock_dir, "import:lock", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                errors = []
                for i, row in enumerate(rows, start=1):
                    if not row.get("gr_id"):
                        errors.append({"row": i, "field": "gr_id", "message": "gr_id is required"})
                    if not row.get("po_id"):
                        errors.append({"row": i, "field": "po_id", "message": "po_id is required"})
                    elif not conn.execute("SELECT 1 FROM pos WHERE po_id = ?", (row["po_id"],)).fetchone():
                        errors.append({"row": i, "field": "po_id", "message": f"PO {row['po_id']} not found"})
                    if row.get("status") and row["status"] not in GR_ALLOWED_STATUSES:
                        errors.append({"row": i, "field": "status", "message": f"Invalid status: {row['status']}"})
                if errors:
                    conn.rollback()
                    return {"ok": False, "errors": errors}

                imported = 0
                for row in rows:
                    conn.execute(
                        """INSERT INTO gr_requests (gr_id, po_id, gr_no, requester_id,
                          estimated_amount, con_value, status, remark, tax_rate,
                          gross_cost, goods_service_description, confirmation_name,
                          delivery_from, delivery_to, last_delivery,
                          created_by, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (row["gr_id"], row["po_id"], row.get("gr_no"), row.get("requester_id"),
                         row["estimated_amount"], row.get("con_value"),
                         row.get("status", "draft"), row.get("remark"), row.get("tax_rate"),
                         row.get("gross_cost"), row.get("goods_service_description"),
                         row.get("confirmation_name"), row.get("delivery_from"),
                         row.get("delivery_to"), row.get("last_delivery"),
                         current_user["user_id"], timestamp),
                    )
                    write_operation_record(conn, action_type="import_gr", object_type="gr",
                        object_id=row["gr_id"], sc_id=None,
                        operator_id=current_user["user_id"],
                        machine_id=current_user["machine_id"], before=None, after=dict(row))
                    imported += 1
                conn.commit()
                return {"ok": True, "count": imported}
            except Exception:
                conn.rollback()
                raise
```

- [ ] **Step 2: Add bridge endpoints for PO and GR import**

Follow the same pattern as `import_scs` and `download_sc_template` in bridge.py, creating:
- `import_pos` / `download_po_template`
- `import_grs` / `download_gr_template`

- [ ] **Step 3: Add frontend buttons to PoListView and GrListView**

Same pattern as Task 6 Step 3. Add import/template buttons to PO and GR list views.

Reuse the `useExport` composable's `save_file` pattern for downloading templates.

- [ ] **Step 4: Commit**

```bash
git add .
git commit -m "feat: add PO and GR import with Excel templates and direct status writes"
```

---

### Task 8: User self-registration (C1+C2)

**Files:**
- Modify: `sc_gr_app/services/user_service.py` (add register_user)
- Modify: `sc_gr_app/api/bridge.py` (add register_user endpoint)
- Modify: `frontend/src/views/LoginView.vue` (add register button + form)
- Modify: `frontend/src/i18n/locales/en-US.js`
- Modify: `frontend/src/i18n/locales/zh-CN.js`

- [ ] **Step 1: Add `register_user` to `user_service.py`**

```python
def register_user(config: AppConfig, machine_id: str, user_name: str, email: str) -> dict:
    """Register a new user with requester role. Only allowed if machine_id is not yet registered."""
    with connect(config) as conn:
        existing = conn.execute(
            "SELECT user_id, machine_id, status FROM users WHERE machine_id = ?",
            (machine_id,),
        ).fetchone()
        if existing:
            raise ValidationError(
                f"Machine ID {machine_id} is already registered. Contact an administrator."
            )

        timestamp = datetime.now(timezone.utc).isoformat()
        user_id = str(uuid4())

        conn.execute(
            """INSERT INTO users (user_id, machine_id, user_name, role, email, status, created_at, updated_at)
               VALUES (?, ?, ?, 'requester', ?, 'active', ?, ?)""",
            (user_id, machine_id, user_name, email, timestamp, timestamp),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row)
```

Add `from uuid import uuid4` import.

- [ ] **Step 2: Add bridge endpoints**

First, add a `detect_machine_id` endpoint that works without authorization (for the registration form to display the current machine ID):

```python
def detect_machine_id(self, _payload=None) -> dict:
    """Return the current machine ID. Works even for unregistered machines."""
    return ok(get_7_digit_id())
```

Then add the `register_user` endpoint:

```python
def register_user(self, payload) -> dict:
    """Register a new user. No auth required — only available for unregistered machines."""
    try:
        payload = self._required_payload(payload)
        machine_id = get_7_digit_id()
        user_name = _require_payload_field(payload, "user_name")
        email = _require_payload_field(payload, "email")

        # Verify this machine is NOT already registered
        try:
            get_user_by_machine_id(self.config, machine_id)
            return fail(ValidationError("This machine is already registered."))
        except PermissionDenied:
            pass  # Expected — machine not registered yet

        user = user_service.register_user(self.config, machine_id, user_name, email)
        return ok(user)
    except ValidationError as e:
        return fail(e)
```

- [ ] **Step 3: Update LoginView.vue — add registration**

In the `unauthorized` state template, add a "Register" button:

```vue
<div v-if="state === 'unauthorized'" class="login-state">
  <el-result icon="error" :title="$t('login.notAuthorized')">
    <!-- ... existing ... -->
    <template #extra>
      <el-button @click="verify">{{ $t('common.retry') }}</el-button>
      <el-button type="primary" @click="showRegister = true">{{ $t('login.register') }}</el-button>
    </template>
  </el-result>
</div>
```

Add registration form dialog:

```vue
<el-dialog v-model="showRegister" :title="$t('login.register')" width="400px">
  <el-form :model="registerForm" label-position="top">
    <el-form-item :label="$t('login.machineId')">
      <el-input :model-value="detectedMachineId" disabled />
    </el-form-item>
    <el-form-item :label="$t('login.userName')" required>
      <el-input v-model="registerForm.user_name" />
    </el-form-item>
    <el-form-item :label="$t('login.email')" required>
      <el-input v-model="registerForm.email" type="email" />
    </el-form-item>
  </el-form>
  <template #footer>
    <el-button @click="showRegister = false">{{ $t('common.cancel') }}</el-button>
    <el-button type="primary" @click="doRegister" :loading="registering">{{ $t('login.register') }}</el-button>
  </template>
</el-dialog>
```

Add script logic:

```js
const showRegister = ref(false)
const detectedMachineId = ref('')
const registering = ref(false)
const registerForm = ref({ user_name: '', email: '' })

async function doRegister() {
  registering.value = true
  try {
    user.value = await callApi('register_user', {
      user_name: registerForm.value.user_name,
      email: registerForm.value.email,
    })
    window.__currentUser = user.value
    state.value = 'authorized'
    showRegister.value = false
  } catch (e) {
    lastError.value = e.message
  } finally {
    registering.value = false
  }
}
```

Set `detectedMachineId` during `verify()` — when the PERMISSION_DENIED error comes back, call `callApi('detect_machine_id')` to get the machine ID for the registration form. Add this call in the `catch` block for PERMISSION_DENIED:

```js
} catch (e) {
    lastError.value = e.message || t('login.unableToReach')
    if (e instanceof ApiError && e.code === 'PERMISSION_DENIED') {
      state.value = 'unauthorized'
      // Fetch machine ID for potential registration
      try {
        detectedMachineId.value = await callApi('detect_machine_id')
      } catch { /* ignore */ }
    }
    // ...
}
```

- [ ] **Step 4: Add i18n keys**

```js
// en-US.js
login: {
  // ... existing
  register: 'Register',
  machineId: 'Machine ID',
  userName: 'Name',
  email: 'Email',
}
// zh-CN.js
login: {
  // ... existing
  register: '注册',
  machineId: '机器ID',
  userName: '姓名',
  email: '邮箱',
}
```

- [ ] **Step 5: Show user_name instead of machine_id in detail views**

In SC/PO/GR detail components, wherever `requester_id` or `operator_id` is displayed, resolve to user_name. This is already partially done via JOINs in the query service. Check `ScDetailCard.vue`, `ScDetailView.vue`, `PoDetailView.vue`, `GrDetailView.vue` — ensure they display `user_name` (or `requester_name` if the backend resolves it) instead of the raw ID.

If the backend doesn't resolve names, add JOIN in `query_service.py` for all entity searches to include `requester_name` from users table.

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "feat: add user self-registration as requester, show names in detail views"
```

---

### Task 9: Email subject convention + body simplification (D1+D2+D3)

**Files:**
- Modify: `sc_gr_app/notification/templates.py` (subject + simplified HTML body)
- Modify: `sc_gr_app/notification/sender.py` (attachment names, field renames)

- [ ] **Step 1: Update `build_subject` in `templates.py`**

Replace the existing `build_subject` with the new naming convention:

```python
def _abbreviate_name(name: str) -> str:
    """Abbreviate a name: 'Zhou, Liwei' → 'ZLiwei', 'Liwei Zhou' → 'LZhou'"""
    if not name:
        return "Unknown"
    # Handle "LastName, FirstName" format
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        surname = parts[0]
        given = parts[1] if len(parts) > 1 else ""
        return f"{surname[0] if surname else ''}{given}"
    # Handle "FirstName LastName" format
    parts = name.strip().split()
    if len(parts) >= 2:
        return f"{parts[0][0] if parts[0] else ''}{parts[-1]}"
    return name

def _daily_seq(conn, date_str: str) -> str:
    """Get the next per-day sequence number for email subjects."""
    row = conn.execute(
        "SELECT COUNT(*) + 1 FROM notification_queue WHERE date(created_at) = ?",
        (date_str,)
    ).fetchone()
    return f"{row[0]:03d}"

def build_subject(entry: dict, entity_info: dict, actor_name: str = "") -> str:
    """Build email subject: [POMP] <action> <entity_type> from <abbr> <YYYYMMDD>-<NNN>"""
    entity_type = entry["entity_type"].upper()
    event_key = entry.get("event_key", "")
    event_type = entry.get("event_type", "")

    if event_type == "status_change":
        action = _TRANSITION_LABELS.get(event_key, event_key)
    elif event_type == "threshold_date":
        months = event_key.replace("threshold_date:", "").replace("m", "")
        action = f"Contract Expiring <{months}m"
    elif event_type == "threshold_amount":
        pct = event_key.replace("threshold_amount:", "").replace("%", "")
        action = f"Budget Exhausting <{pct}%"
    else:
        action = event_key

    abbr = _abbreviate_name(actor_name) if actor_name else "System"
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    # seq is set by the caller (sender.py) and passed through entry context

    return f"[POMP] {action} {entity_type} from {abbr} {today}"
```

Note: The sequence number `-NNN` requires DB access, so it is appended by `sender.py` after calling `build_subject`. In `send_entry` (and `generate_draft`), after `subject = templates.build_subject(entry, entity_info, actor_name=actor_name)`, add:

```python
# Append daily sequence number
today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
seq = conn.execute(
    "SELECT COUNT(*) + 1 FROM notification_queue WHERE date(created_at) = date('now')"
).fetchone()[0]
subject = f"{subject}-{seq:03d}"
```

- [ ] **Step 2: Simplify `build_body` — two-table format**

Replace the current HTML-rich body with a simple two-table format:

```python
def build_body(entry: dict, entity_info: dict, user_emails: dict,
               actor_name: str = "", requester_name: str = "") -> str:
    """Build simplified email body with two tables: Notification Info + Detail Info."""
    entity_type = entry["entity_type"]
    entity_id = entry["entity_id"]
    event_key = entry.get("event_key", "")
    event_type = entry.get("event_type", "")

    type_label = _TYPE_LABELS.get(entity_type, entity_type)
    status_value = entity_info.get("status", "")
    if status_value == "manager_confirm":
        status_display = "To be confirm"
    else:
        status_display = _STATUS_LABELS.get(status_value, status_value)

    event_desc = _describe_event(event_type, event_key)

    # Get attachment names
    attachments = entity_info.get("_attachments", [])
    attachment_str = ", ".join(attachments) if attachments else "None"

    # Table 1: Notification Info
    lines = []
    lines.append('<table style="width:100%;border-collapse:collapse;font-family:Arial,sans-serif;font-size:14px;margin-bottom:20px">')
    lines.append('<tr><th colspan="2" style="background:#f5f5f5;padding:8px;text-align:left;border:1px solid #ddd">Notification Info</th></tr>')
    for label, value in [
        ("Entity Type", type_label),
        ("Entity ID", entity_id),
        ("Event", event_desc),
        ("Operator", actor_name or "-"),
        ("Status", status_display),
        ("Attachments", attachment_str),
    ]:
        lines.append(f'<tr><td style="padding:8px;border:1px solid #ddd;font-weight:600;width:140px">{label}</td><td style="padding:8px;border:1px solid #ddd">{value}</td></tr>')
    lines.append('</table>')

    # Table 2: Detail Info (all entity fields)
    lines.append('<table style="width:100%;border-collapse:collapse;font-family:Arial,sans-serif;font-size:14px">')
    lines.append('<tr><th colspan="2" style="background:#f5f5f5;padding:8px;text-align:left;border:1px solid #ddd">Detail Info</th></tr>')
    for key, value in _entity_fields(entity_type, entity_info):
        lines.append(f'<tr><td style="padding:8px;border:1px solid #ddd;font-weight:600;width:160px">{key}</td><td style="padding:8px;border:1px solid #ddd">{value if value is not None else "-"}</td></tr>')
    lines.append('</table>')

    return "\n".join(lines)
```

- [ ] **Step 3: Add `_entity_fields` helper with field removals and renames**

```python
# Fields to EXCLUDE from emails
_SC_EXCLUDE = {"consumed_amount", "sc_available_amount", "created_at", "updated_at",
               "pending_date", "approved_date", "closed_at"}
_PO_EXCLUDE = {"consumed_amount", "pending_total", "pending_total_incl_tax",
               "open_po_amount", "activing_date", "created_at", "updated_at"}
_GR_EXCLUDE = {"created_at", "pending_date", "approved_date", "cancelled_at", "confirmed_at"}

# Field label renames
_GR_RENAMES = {
    "estimated_amount": "GR Application Amount (Net)",
    "gross_cost": "GR Application Amount (Gross)",
    "con_value": "GR Value",
}
_PO_RENAMES = {
    "pending_total": "Pending GR amount (Net)",
    "pending_total_incl_tax": "Pending GR amount (Gross)",
}

def _entity_fields(entity_type: str, entity_info: dict) -> list[tuple[str, str]]:
    """Return (label, value) pairs for entity detail table, filtered and renamed."""
    if entity_type == "sc":
        exclude = _SC_EXCLUDE
        renames = {}
    elif entity_type == "po":
        exclude = _PO_EXCLUDE
        renames = _PO_RENAMES
    else:
        exclude = _GR_EXCLUDE
        renames = _GR_RENAMES

    result = []
    for key, value in entity_info.items():
        if key.startswith("_"):
            continue
        if key in exclude:
            continue
        label = renames.get(key, key.replace("_", " ").title())
        result.append((label, value))
    return result
```

- [ ] **Step 4: Update `sender.py` — attachment names and requester-only reminders**

In `send_entry`, already queries attachment rows. Add attachment filenames to entity_info before building body:

```python
attachment_rows = conn.execute(
    "SELECT filename FROM attachments WHERE entity_type = ? AND entity_id = ?",
    (entity_type, entity_id),
).fetchall()
entity_info["_attachments"] = [r["filename"] for r in attachment_rows]
```

For reminders (threshold_date, threshold_amount, custom_schedule): ensure only the requester is in `to_recipients`, not admins.

In `sc_gr_app/notification/thresholds.py` line 57, change:

```python
# Old (line 57):
to_ids = [requester_id] + admin_recipients

# New:
to_ids = [requester_id]
```

Also in `sc_gr_app/notification/schedules.py` line 59, make the same change:

```python
# Old (line 59):
to_ids = [requester_id] + admin_recipients

# New:
to_ids = [requester_id]
```

No other changes needed in schedules.py.

- [ ] **Step 5: Update `_STATUS_LABELS`**

```python
_STATUS_LABELS["manager_confirm"] = "To be confirm"
```

- [ ] **Step 6: Commit**

```bash
git add sc_gr_app/notification/
git commit -m "refactor: simplify email to two-table format, new subject convention, field renames"
```

---

### Task 10: Email draft preview + manual send (D4)

**Files:**
- Modify: `sc_gr_app/notification/sender.py` (add generate_draft function)
- Modify: `sc_gr_app/api/bridge.py` (add generate_email_draft endpoint)
- Create: `frontend/src/components/notification/EmailPreviewDialog.vue`
- Modify: `frontend/src/views/MailView.vue` or relevant parent view (integrate preview dialog)

- [ ] **Step 1: Add `generate_draft` to sender.py**

```python
def generate_draft(conn: sqlite3.Connection, entry: dict) -> dict:
    """Generate email content for preview without sending.
    Returns {subject, html_body, to_addresses, cc_addresses, attachments}."""
    to_ids = json.loads(entry["to_recipients"])
    cc_ids = json.loads(entry["cc_recipients"])
    to_emails_map = resolve_emails(conn, to_ids)
    cc_emails_map = resolve_emails(conn, cc_ids)
    to_addresses = [to_emails_map[uid] for uid in to_ids if uid in to_emails_map]
    cc_addresses = [cc_emails_map[uid] for uid in cc_ids if uid in cc_emails_map]

    entity_type = entry["entity_type"]
    entity_id = entry["entity_id"]
    entity_info = {}
    if entity_type == "sc":
        row = conn.execute("SELECT * FROM sc_records WHERE sc_id = ?", (entity_id,)).fetchone()
    elif entity_type == "po":
        row = conn.execute(
            """SELECT p.*, v.vendor_name FROM pos p
               LEFT JOIN vendors v ON v.vendor_id = p.vendor_id
               WHERE p.po_id = ?""", (entity_id,)
        ).fetchone()
    elif entity_type == "gr":
        row = conn.execute("SELECT * FROM gr_requests WHERE gr_id = ?", (entity_id,)).fetchone()
    else:
        row = None
    if row:
        entity_info = dict(row)

    _attach_budget_info(conn, entity_type, entity_id, entity_info)

    actor_id = entry.get("actor_id") or ""
    actor_name = resolve_user_name(conn, actor_id) if actor_id else ""
    requester_id = entity_info.get("requester_id") or ""
    requester_name = resolve_user_name(conn, requester_id) if requester_id else ""

    subject = templates.build_subject(entry, entity_info, actor_name=actor_name)
    body = templates.build_body(entry, entity_info, {**to_emails_map, **cc_emails_map},
                                actor_name=actor_name, requester_name=requester_name)

    attachment_rows = conn.execute(
        "SELECT filename, stored_path FROM attachments WHERE entity_type = ? AND entity_id = ?",
        (entity_type, entity_id),
    ).fetchall()
    attachments = [r["filename"] for r in attachment_rows]
    attachment_paths = [r["stored_path"] for r in attachment_rows]

    return {
        "subject": subject,
        "html_body": body,
        "to_addresses": to_addresses,
        "cc_addresses": cc_addresses,
        "attachments": attachments,
        "attachment_paths": attachment_paths,
        "entry_id": entry["id"],
    }
```

- [ ] **Step 2: Add bridge endpoint**

```python
def generate_email_draft(self, payload) -> dict:
    """Generate email content for preview. Returns draft data."""
    try:
        user = get_user_by_machine_id(self.config, get_7_digit_id())
        payload = self._required_payload(payload)
        entry_id = _require_payload_field(payload, "entry_id")

        with connect(self.config) as conn:
            entry = conn.execute(
                "SELECT * FROM notification_queue WHERE id = ?", (entry_id,)
            ).fetchone()
            if not entry:
                return fail(NotFound(f"Queue entry {entry_id} not found"))
            draft = sender.generate_draft(conn, dict(entry))
            return ok(draft)
    except (PermissionDenied, ValidationError, NotFound) as e:
        return fail(e)

def open_email_draft_in_outlook(self, payload) -> dict:
    """Generate email via Outlook COM and open in Outlook for manual send."""
    try:
        user = get_user_by_machine_id(self.config, get_7_digit_id())
        payload = self._required_payload(payload)
        entry_id = _require_payload_field(payload, "entry_id")

        import pythoncom
        import win32com.client

        with connect(self.config) as conn:
            entry = conn.execute(
                "SELECT * FROM notification_queue WHERE id = ?", (entry_id,)
            ).fetchone()
            if not entry:
                return fail(NotFound(f"Queue entry {entry_id} not found"))
            draft = sender.generate_draft(conn, dict(entry))

        pythoncom.CoInitialize()
        try:
            outlook = win32com.client.Dispatch("Outlook.Application")
            mail = outlook.CreateItem(0)
            mail.Subject = draft["subject"]
            mail.HTMLBody = draft["html_body"]
            mail.To = "; ".join(draft["to_addresses"])
            if draft["cc_addresses"]:
                mail.CC = "; ".join(draft["cc_addresses"])
            # Use attachment_paths from generate_draft to attach files
            for att_path in draft["attachment_paths"]:
                try:
                    mail.Attachments.Add(att_path)
                except Exception:
                    pass
            mail.Save()
            mail.Display()
        finally:
            pythoncom.CoUninitialize()

        return ok({"message": "Draft opened in Outlook"})
    except (PermissionDenied, ValidationError, NotFound) as e:
        return fail(e)
```

- [ ] **Step 3: Create frontend `EmailPreviewDialog.vue`**

```vue
<template>
  <el-dialog v-model="visible" title="Email Preview" width="700px" top="5vh">
    <div v-if="draft">
      <div style="margin-bottom:12px">
        <strong>Subject:</strong> {{ draft.subject }}
      </div>
      <div style="margin-bottom:12px">
        <strong>To:</strong> {{ draft.to_addresses.join(', ') }}<br/>
        <strong>Cc:</strong> {{ draft.cc_addresses.join(', ') || 'None' }}
      </div>
      <div style="margin-bottom:12px">
        <strong>Attachments:</strong> {{ draft.attachments.join(', ') || 'None' }}
      </div>
      <div v-html="draft.html_body" style="border:1px solid #ddd;padding:16px;max-height:400px;overflow:auto"></div>
    </div>
    <template #footer>
      <el-button @click="visible = false">Cancel</el-button>
      <el-button type="primary" @click="openInOutlook" :loading="sending">Open in Outlook</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { callApi } from '@/api/bridge.js'

const props = defineProps({ entryId: Number })
const emit = defineEmits(['sent'])
const visible = ref(false)
const draft = ref(null)
const sending = ref(false)

async function show() {
  visible.value = true
  draft.value = await callApi('generate_email_draft', { entry_id: props.entryId })
}

async function openInOutlook() {
  sending.value = true
  try {
    await callApi('open_email_draft_in_outlook', { entry_id: props.entryId })
    visible.value = false
    emit('sent')
  } finally {
    sending.value = false
  }
}

defineExpose({ show })
</script>
```

- [ ] **Step 4: Integrate dialog in MailView or parent**

In the view that shows email notification queue items, add the EmailPreviewDialog component and wire a "Preview & Send" button for each non-auto (status_change type) entry. Auto entries (threshold, custom_schedule) should show as "Sent automatically" without preview.

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: email draft preview dialog, open in Outlook for manual send"
```

---

### Task 11: Default language + date columns + PO deadline rename (E1+E2+E5)

**Files:**
- Modify: `frontend/src/i18n/index.js` (default locale)
- Modify: `frontend/src/views/ScListView.vue` (add date columns)
- Modify: `frontend/src/views/PoListView.vue` (add date columns)
- Modify: `frontend/src/components/sc/ScTable.vue` (or wherever SC list table is defined)
- Modify: `frontend/src/components/po/PoTable.vue` (or wherever PO list table is defined)
- Modify: `frontend/src/components/po/GrFormDialog.vue` (Contract Value → GR Value label)
- Modify: `frontend/src/views/GrDetailView.vue` (Contract Value → GR Value label)
- Modify: `frontend/src/i18n/locales/en-US.js` (deadline → contract end date, Contract Value → GR Value)
- Modify: `frontend/src/i18n/locales/zh-CN.js` (截止日期 → 合同结束日期, Contract Value → GR Value)

- [ ] **Step 1: Change default locale**

In `frontend/src/i18n/index.js`:
```js
const locale = saved || 'en-US'
```

- [ ] **Step 2: Add date columns to SC list**

In `ScTable.vue`, add `service_period_start` and `service_period_end` columns. Currently the SC table has no date columns. Add after the `sc_amount` column (or between `sc_amount` and `created_at`):

```vue
<el-table-column prop="service_period_start" :label="$t('sc.startDate')" sortable="custom" width="120">
  <template #default="{ row }">{{ formatDate(row.service_period_start) }}</template>
</el-table-column>
<el-table-column prop="service_period_end" :label="$t('sc.endDate')" sortable="custom" width="120">
  <template #default="{ row }">{{ formatDate(row.service_period_end) }}</template>
</el-table-column>
```

- [ ] **Step 3: Rename PO date column labels**

`PoTable.vue` already has `contract_from` and `contract_to` columns (lines 28-33). They currently use i18n keys `po.contractFrom` and `po.contractTo`. Change the column props to use `$t('po.startDate')` and `$t('po.contractEndDate')` respectively.

Current code at line 28-33:
```vue
<el-table-column prop="contract_from" :label="$t('po.contractFrom')" width="120" sortable>
<el-table-column prop="contract_to" :label="$t('po.contractTo')" width="120" sortable>
```

Change `$t('po.contractFrom')` → `$t('po.startDate')` and `$t('po.contractTo')` → `$t('po.contractEndDate')`.

- [ ] **Step 4: Update i18n keys**

```js
// en-US.js
sc: { startDate: 'Start Date', endDate: 'End Date' }
po: { startDate: 'Start Date', contractEndDate: 'Contract End Date' }
gr: { grValue: 'GR Value' }
// zh-CN.js
sc: { startDate: '开始日期', endDate: '结束日期' }
po: { startDate: '开始日期', contractEndDate: '合同结束日期' }
gr: { grValue: 'GR Value' }
```

Also search for any remaining "Deadline" or "截止日期" references in i18n files and update them. Search for "Contract Value" in GR form and detail components and replace with "GR Value".

- [ ] **Step 5: Update GR form label**

In `GrFormDialog.vue`, change the `con_value` field label from "Contract Value" to "GR Value" (using the i18n key `$t('gr.grValue')`).

- [ ] **Step 6: Update GR detail view**

In `GrDetailView.vue`, change the `con_value` field label similarly.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/i18n/ frontend/src/views/ScListView.vue frontend/src/views/PoListView.vue frontend/src/components/sc/ScTable.vue frontend/src/components/po/PoTable.vue frontend/src/components/po/GrFormDialog.vue frontend/src/views/GrDetailView.vue
git commit -m "feat: default English, add date columns to SC/PO lists, rename PO deadline to contract end date, GR Contract Value to GR Value"
```

---

### Task 12: Vendor selection display (E3+E4)

**Files:**
- Modify: `frontend/src/components/sc/ScVendorSection.vue` (vendor display format)
- Modify: `frontend/src/components/po/PoFormDialog.vue` (vendor display format)
- Modify: `frontend/src/components/sc/VendorPickerDialog.vue` (vendor display format)

- [ ] **Step 1: Update vendor display format**

In all vendor selection dropdowns, change the display format from `vendor_name - vendor_id` to `vendor_name - company_name_cn - vendor_id - ksrm_vendor_code`.

In vendor dropdown option templates:

```vue
<el-option
  v-for="v in vendorOptions"
  :key="v.vendor_id"
  :label="`${v.vendor_name} - ${v.company_name_cn || '-'} - ${v.vendor_id} - ${v.ksrm_vendor_code || '-'}`"
  :value="v.vendor_id"
/>
```

- [ ] **Step 2: Update vendor detail display in SC/PO forms**

When displaying the selected vendor name (not in dropdown), use the same format.

- [ ] **Step 3: Update VendorFormDialog labels**

Ensure `vendor_name` label shows "(Full Name Required)" hint as per Task 2. Remove vendor_id from create form (already done in Task 2).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/sc/ScVendorSection.vue frontend/src/components/po/PoFormDialog.vue frontend/src/components/sc/VendorPickerDialog.vue
git commit -m "feat: vendor display format with name-CN-ID-KSRM, full-name label hint"
```

---

### Task 13: Installer versioning + PO deadline label (E7)

**Files:**
- Modify: `packaging/build.ps1` (non-versioned copy + history archive)

- [ ] **Step 1: Update build.ps1**

After the Inno Setup step and before pushing to shared drive, add:

```powershell
# Copy non-versioned installer to release/ (overwrite)
$installerDir = Join-Path $distDir "installer"
$nonVersionedInstaller = Join-Path $distDir "installer\$setupPrefix-Setup.exe"
if (Test-Path $guiPath) {
    Copy-Item -Path $guiPath -Destination $nonVersionedInstaller -Force
    Write-Host "Non-versioned installer: $nonVersionedInstaller" -ForegroundColor Green
}

# Copy versioned installer to release/history/
$historyDir = Join-Path $distDir "installer\history"
if (-not (Test-Path $historyDir)) {
    New-Item -ItemType Directory -Path $historyDir -Force | Out-Null
}
if (Test-Path $guiPath) {
    Copy-Item -Path $guiPath -Destination (Join-Path $historyDir $guiInstaller) -Force
    Write-Host "History installer: $historyDir\$guiInstaller" -ForegroundColor Green
}
```

Also copy the non-versioned and history installers to the shared drive:

```powershell
# Copy non-versioned installer to shared drive
$nonVersionedName = "$setupPrefix-Setup.exe"
Copy-Item -Path $nonVersionedInstaller -Destination (Join-Path $sharedReleases $nonVersionedName) -Force

# Create history directory on shared drive and copy versioned there
$sharedHistory = Join-Path $sharedReleases "history"
if (-not (Test-Path $sharedHistory)) {
    New-Item -ItemType Directory -Path $sharedHistory -Force | Out-Null
}
Copy-Item -Path $guiPath -Destination (Join-Path $sharedHistory $guiInstaller) -Force
```

- [ ] **Step 2: Update update.py — check fixed path**

Ensure the auto-update logic checks for `POMP-Setup.exe` (non-versioned) at a fixed path. Read `sc_gr_app/update.py` and update the manifest/URL logic if needed to always check the non-versioned installer path.

- [ ] **Step 3: Commit**

```bash
git add packaging/build.ps1
git commit -m "feat: produce non-versioned installer + history archive, fix update path"
```

---

### Task 14: Final verification and integration test

**Files:** N/A (testing only)

- [ ] **Step 1: Run all tests**

```bash
uv run pytest -q
```

- [ ] **Step 2: Build the app**

```bash
powershell -ExecutionPolicy Bypass -File packaging/build.ps1
```

- [ ] **Step 3: Manual smoke test checklist**

- [ ] Launch app, verify default language is English
- [ ] Register a new user (if possible) or verify login flow
- [ ] Create SC with currency selection, no vendor
- [ ] Verify bilingual vendor prompt on SC form
- [ ] Create vendor — verify auto-generated vendor_id
- [ ] Import SC/PO/GR from templates
- [ ] Check vendor display format in PO form
- [ ] Check SC/PO list date columns
- [ ] Check "Contract End Date" label on PO
- [ ] Perform an action that triggers status_change email → verify preview dialog
- [ ] Check email subject format
- [ ] Check email body has two simple tables
- [ ] Check "Operation Record" naming in nav/sidebar
- [ ] Check timestamp format YYYY-MM-DD HH:MM:SS

- [ ] **Step 4: Fix any issues found and final commit**

---
