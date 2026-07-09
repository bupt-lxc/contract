# Service Scope 调整及 Request Type 重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename vendor service_scope values, remap SC request_type from 4 to 3 values, and add an optional service_scope field to SC records.

**Architecture:** Database migration (v35) performs data cleanup + table rebuild first. Backend services are updated next (validation sets, CRUD fields, import/export). Frontend components are updated last (dropdown options, display labels). A shared `requestTypeLabel()` utility ensures consistent display across all components.

**Tech Stack:** Python (SQLite via sqlite3, Flask-like API), Vue 3 (Element Plus, Vue I18n)

---

### Task 1: Database migration v35

**Files:**
- Modify: `sc_gr_app/db/migrations.py` (SCHEMA_VERSION, V1_SQL, new `_migrate_v35`, dispatch chain)

- [ ] **Step 1: Bump SCHEMA_VERSION and add v35 migration function**

At line 9, change `SCHEMA_VERSION = 34` to `SCHEMA_VERSION = 35`.

Add `_migrate_v35` before the `migrate()` function (after `_migrate_v34` at line 1562):

```python
def _migrate_v35(conn) -> None:
    """Adjust service_scope values, remap request_type, add service_scope to sc_records."""
    # Step A: Data cleanup — vendor service_scope rename
    conn.execute(
        "UPDATE vendors SET service_scope = 'Engineering Service' "
        "WHERE service_scope = 'engineering Service'"
    )
    conn.execute(
        "UPDATE vendors SET service_scope = 'Maintenance&Calibration' "
        "WHERE service_scope = 'Maintenance'"
    )

    # Step B: Data cleanup — sc_vendors snapshot JSON update
    conn.execute(
        "UPDATE sc_vendors SET vendor_snapshot = json_set("
        "  vendor_snapshot, '$.service_scope', 'Engineering Service'"
        ") WHERE json_extract(vendor_snapshot, '$.service_scope') = 'engineering Service'"
    )
    conn.execute(
        "UPDATE sc_vendors SET vendor_snapshot = json_set("
        "  vendor_snapshot, '$.service_scope', 'Maintenance&Calibration'"
        ") WHERE json_extract(vendor_snapshot, '$.service_scope') = 'Maintenance'"
    )

    # Step C: Data cleanup — request_type old→new mapping
    conn.execute(
        "UPDATE sc_records SET request_type = 'new' "
        "WHERE request_type IN ('material', 'service', 'fixed_asset')"
    )

    # Step D: Four-table rebuild (follows v34 pattern)
    # SC records get CHECK constraint update + new service_scope column.
    # pos, gr_requests, sc_vendors rebuild is required because SQLite
    # invalidates FK references when sc_records is renamed.
    has_pos = _table_exists(conn, "pos")
    has_sc = _table_exists(conn, "sc_records")
    has_gr = _table_exists(conn, "gr_requests")
    has_sv = _table_exists(conn, "sc_vendors")

    # Phase 1: Rename all affected tables
    if has_pos:
        conn.execute("ALTER TABLE pos RENAME TO pos_old")
    if has_sc:
        conn.execute("ALTER TABLE sc_records RENAME TO sc_records_old")
        sc_old_cols = {row["name"] for row in conn.execute("PRAGMA table_info(sc_records_old)")}
        sc_has_submitted = "submitted_date" in sc_old_cols
        sc_has_calloff = "calloff_po_id" in sc_old_cols
    if has_gr:
        conn.execute("ALTER TABLE gr_requests RENAME TO gr_requests_old")
    if has_sv:
        conn.execute("ALTER TABLE sc_vendors RENAME TO sc_vendors_old")
        sv_cols = {row["name"] for row in conn.execute("PRAGMA table_info(sc_vendors_old)")}
        sv_has_snapshot = "vendor_snapshot" in sv_cols

    # Phase 2: Create new tables
    if has_pos:
        conn.execute("""
            CREATE TABLE pos (
              po_id TEXT PRIMARY KEY,
              sc_id TEXT REFERENCES sc_records(sc_id),
              vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
              po_no TEXT,
              requester_id TEXT,
              po_amount REAL NOT NULL CHECK (po_amount > 0),
              status TEXT NOT NULL CHECK (status IN ('draft','active','finished')),
              contract_from TEXT,
              contract_to TEXT,
              contract_no TEXT,
              payment_frequency TEXT,
              contract_pos TEXT,
              contract_type TEXT,
              cost_center TEXT,
              purchaser TEXT,
              active_date TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              finished_at TEXT,
              finished_by TEXT REFERENCES users(user_id),
              request_type TEXT CHECK (request_type IN ('FC'))
            )
        """)

    if has_sc:
        sc_sql = """
            CREATE TABLE sc_records (
              sc_id TEXT PRIMARY KEY,
              sc_no TEXT,
              requester_id TEXT NOT NULL REFERENCES users(user_id),
              request_type TEXT CHECK (request_type IN ('FC', 'call_off', 'new')),
              cost_center INTEGER,
              sc_amount REAL CHECK (sc_amount IS NULL OR sc_amount > 0),
              service_period_start TEXT,
              service_period_end TEXT,
              status TEXT NOT NULL CHECK (status IN ('draft', 'manager_confirm', 'pending', 'approved', 'denied', 'finished')),
              description TEXT,
              created_by TEXT NOT NULL REFERENCES users(user_id),
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              approved_by TEXT REFERENCES users(user_id),
              approved_at TEXT,
              finished_at TEXT,
              confirmed_at TEXT,
              asset TEXT NOT NULL DEFAULT 'N',
              asset_nums TEXT,
              pending_date TEXT,
              approved_date TEXT,
              internal_system_number TEXT,
              currency TEXT NOT NULL DEFAULT 'CNY',
              service_scope TEXT
        """
        if sc_has_submitted:
            sc_sql += ",\n              submitted_date TEXT"
        if sc_has_calloff:
            sc_sql += ",\n              calloff_po_id TEXT REFERENCES pos(po_id)"
        sc_sql += """,
              CHECK (
                status = 'draft'
                OR status = 'manager_confirm'
                OR (
                  request_type IS NOT NULL
                  AND cost_center IS NOT NULL
                  AND sc_amount IS NOT NULL
                  AND service_period_start IS NOT NULL
                  AND service_period_end IS NOT NULL
                )
              )
            )
        """
        conn.execute(sc_sql)

    if has_gr:
        conn.execute("""
            CREATE TABLE gr_requests (
              gr_id TEXT PRIMARY KEY,
              gr_no TEXT,
              po_id TEXT NOT NULL REFERENCES pos(po_id),
              requester_id TEXT NOT NULL REFERENCES users(user_id),
              estimated_amount REAL NOT NULL CHECK (estimated_amount > 0),
              con_value REAL CHECK (con_value >= 0),
              gross_cost REAL,
              tax_rate REAL,
              status TEXT NOT NULL CHECK (status IN ('draft','manager_confirm','pending','approved','denied','finished')),
              remark TEXT,
              created_by TEXT NOT NULL REFERENCES users(user_id),
              created_at TEXT NOT NULL,
              approved_by TEXT REFERENCES users(user_id),
              approved_at TEXT,
              denied_by TEXT REFERENCES users(user_id),
              denied_at TEXT,
              finished_by TEXT REFERENCES users(user_id),
              finished_at TEXT,
              confirmed_at TEXT,
              pending_date TEXT,
              approved_date TEXT,
              submitted_date TEXT,
              goods_service_description TEXT,
              confirmation_name TEXT,
              delivery_from TEXT,
              delivery_to TEXT,
              last_delivery TEXT,
              updated_at TEXT
            )
        """)

    if has_sv:
        sv_sql = """
            CREATE TABLE sc_vendors (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              sc_id TEXT NOT NULL REFERENCES sc_records(sc_id) ON DELETE CASCADE,
              vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id)
        """
        if sv_has_snapshot:
            sv_sql += ",\n              vendor_snapshot TEXT"
        sv_sql += """,
              UNIQUE(sc_id, vendor_id)
            )
        """
        conn.execute(sv_sql)

    # Phase 3: Copy data
    if has_pos:
        conn.execute("""
            INSERT INTO pos SELECT * FROM pos_old
        """)
    if has_sc:
        # Explicit column list needed because new table has service_scope which old table lacks.
        # Omitted columns (service_scope) default to NULL.
        conn.execute("""
            INSERT INTO sc_records (
              sc_id, sc_no, requester_id, request_type, cost_center,
              sc_amount, service_period_start, service_period_end,
              status, description, created_by, created_at, updated_at,
              approved_by, approved_at, finished_at, confirmed_at,
              asset, asset_nums, pending_date, approved_date,
              internal_system_number, currency
        """
        + (", submitted_date" if sc_has_submitted else "") +
        (", calloff_po_id" if sc_has_calloff else "") +
        """)
            SELECT
              sc_id, sc_no, requester_id, request_type, cost_center,
              sc_amount, service_period_start, service_period_end,
              status, description, created_by, created_at, updated_at,
              approved_by, approved_at, finished_at, confirmed_at,
              asset, asset_nums, pending_date, approved_date,
              internal_system_number, currency
        """
        + (", submitted_date" if sc_has_submitted else "") +
        (", calloff_po_id" if sc_has_calloff else "") +
        " FROM sc_records_old"
        )
    if has_gr:
        conn.execute("INSERT INTO gr_requests SELECT * FROM gr_requests_old")
    if has_sv:
        conn.execute("INSERT INTO sc_vendors SELECT * FROM sc_vendors_old")

    # Phase 4: Drop old tables
    if has_pos:
        conn.execute("DROP TABLE pos_old")
    if has_sc:
        conn.execute("DROP TABLE sc_records_old")
    if has_gr:
        conn.execute("DROP TABLE gr_requests_old")
    if has_sv:
        conn.execute("DROP TABLE sc_vendors_old")

    # Phase 5: Recreate indexes
    if has_pos:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_sc ON pos(sc_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_vendor ON pos(vendor_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_status ON pos(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_requester ON pos(requester_id)")
    if has_sc:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sc_records_requester ON sc_records(requester_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sc_records_status ON sc_records(status)")
    if has_gr:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_po ON gr_requests(po_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_status ON gr_requests(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_requester ON gr_requests(requester_id)")
    if has_sv:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sc_vendors_sc ON sc_vendors(sc_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sc_vendors_vendor ON sc_vendors(vendor_id)")

    _record(conn, 35)
```

- [ ] **Step 2: Update V1_SQL CHECK constraints**

In the `V1_SCHEMA_SQL` string (around line 30-71), update:
- `request_type TEXT CHECK (request_type IN ('material', 'service', 'fixed_asset', 'FC'))` → `request_type TEXT CHECK (request_type IN ('FC', 'call_off', 'new'))`
- Add `service_scope TEXT` column after `currency TEXT NOT NULL DEFAULT 'CNY'`
- In the vendors CHECK constraint, update `'engineering Service'` → `'Engineering Service'` and `'Maintenance'` → `'Maintenance&Calibration'`

- [ ] **Step 3: Register v35 in the migrate() dispatch chain**

At the end of `migrate()` (around line 1748, after `_migrate_v34(conn)`), add:

```python
if max_applied < 35:
    _migrate_v35(conn)
```

Also add the version jump guard in the re-check loop: add `35` to the appropriate skip section near `34`. (Follow the existing pattern with `_table_exists` guard for `sc_records`.)

- [ ] **Step 4: Run existing migration tests to confirm v34 still passes**

```bash
cd c:/Users/V2SE7PP/Projects/contract && python -m pytest tests/test_migrations.py -v
```

Expected: All existing tests pass (v1-v34). v35 test will be added in Task 12.

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/db/migrations.py
git commit -m "feat: add v35 migration for service_scope rename and request_type remap"
```

---

### Task 2: Backend — Update SUPPORTED_SERVICE_SCOPES and vendor import validation

**Files:**
- Modify: `sc_gr_app/services/vendor_service.py:15-31` (SUPPORTED_SERVICE_SCOPES)
- Modify: `sc_gr_app/services/vendor_service.py:449-450` (preview_import service_scope validation)
- Modify: `sc_gr_app/services/vendor_service.py:513-517` (execute_import service_scope validation)

- [ ] **Step 1: Update SUPPORTED_SERVICE_SCOPES**

Replace lines 15-31:

```python
SUPPORTED_SERVICE_SCOPES = {
    "Transportation",
    "Engineering Service",
    "Equipment",
    "Parts",
    "Driver",
    "Test car rental",
    "General Service",
    "Dealers",
    "Import&Export&cusoms clearance",
    "Insurance",
    "Harness",
    "Maintenance&Calibration",
    "Security",
    "Testing support",
    "Others",
}
```

- [ ] **Step 2: Add service_scope value validation in preview_import**

After the existing `if not rec.get("service_scope", "").strip():` check at line 449, add value validation:

```python
scope = rec.get("service_scope", "").strip()
if not scope:
    errors_list.append("service_scope is required")
elif scope not in SUPPORTED_SERVICE_SCOPES:
    errors_list.append(f"service_scope '{scope}' is not a valid value")
```

- [ ] **Step 3: Add service_scope value validation in execute_import**

After line 513 (`scope = rec.get("service_scope", "").strip()`), add below the `if not vname or not scope:` block:

```python
if scope and scope not in SUPPORTED_SERVICE_SCOPES:
    skipped += 1
    errors.append(f"Row {i + 1}: service_scope '{scope}' is invalid, skipped")
    continue
```

Place this check after the existing `if not vname or not scope:` check at line 514-516 but before the `conn.execute("BEGIN IMMEDIATE")`.

- [ ] **Step 4: Run vendor service tests**

```bash
cd c:/Users/V2SE7PP/Projects/contract && python -m pytest tests/test_vendor_service.py -v
```

Expected: Tests pass. Tests that use old values will be updated in Task 12.

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/services/vendor_service.py
git commit -m "feat: update SUPPORTED_SERVICE_SCOPES and add import validation"
```

---

### Task 3: Backend — Update SC request_type validation and add service_scope field

**Files:**
- Modify: `sc_gr_app/services/sc_service.py:30` (SUPPORTED_REQUEST_TYPES)
- Modify: `sc_gr_app/services/sc_service.py:33-46` (OPTIONAL_UPDATE_FIELDS)
- Modify: `sc_gr_app/services/sc_service.py:68-106` (_validate_calloff_po)

- [ ] **Step 1: Update SUPPORTED_REQUEST_TYPES**

Line 30, change:
```python
SUPPORTED_REQUEST_TYPES = {"material", "service", "fixed_asset", "FC"}
```
to:
```python
SUPPORTED_REQUEST_TYPES = {"FC", "call_off", "new"}
```

- [ ] **Step 2: Add service_scope to OPTIONAL_UPDATE_FIELDS**

Line 33-46, add `"service_scope"` to the tuple:

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
    "service_scope",
)
```

- [ ] **Step 3: Update _validate_calloff_po for call_off request_type**

Replace the function (lines 68-106) with:

```python
def _validate_calloff_po(conn, calloff_po_id: str | None, request_type: str | None, sc_amount, exclude_sc_id: str | None = None) -> None:
    """Validate call-off PO reference for call-off SC creation/submit."""
    if request_type == "call_off":
        if calloff_po_id is None:
            raise ValidationError("call_off request_type requires calloff_po_id")
    elif calloff_po_id is not None:
        raise ValidationError("calloff_po_id is only valid for call_off request_type")

    if calloff_po_id is None:
        if request_type == "FC":
            return
        return  # 'new' or 'call_off' without calloff_po_id handled above

    po_row = conn.execute(
        """select po.po_id, po.po_amount, po.status, sc.request_type as parent_sc_type,
                  po.request_type as po_request_type
           from pos po
           left join sc_records sc on sc.sc_id = po.sc_id
           where po.po_id = ?""",
        (calloff_po_id,),
    ).fetchone()
    if po_row is None:
        raise NotFound(f"PO not found: {calloff_po_id}")
    is_fc_po = (po_row["po_request_type"] == "FC" or po_row["parent_sc_type"] == "FC")
    if not is_fc_po:
        raise ValidationError("Call-off PO must belong to an FC-type SC or be an independent FC PO")
    if po_row["status"] != "active":
        raise ConflictError("Call-off PO must be active to create call-off SCs")

    if exclude_sc_id is not None:
        calloff_total = conn.execute(
            "select coalesce(sum(sc_amount), 0) from sc_records where calloff_po_id = ? and sc_id != ?",
            (calloff_po_id, exclude_sc_id),
        ).fetchone()[0]
    else:
        calloff_total = conn.execute(
            "select coalesce(sum(sc_amount), 0) from sc_records where calloff_po_id = ?",
            (calloff_po_id,),
        ).fetchone()[0]
    new_amount = Decimal(str(sc_amount)) if sc_amount is not None else Decimal("0")
    if Decimal(str(calloff_total)) + new_amount > Decimal(str(po_row["po_amount"])):
        raise ConflictError("Call-off SC total would exceed PO(FC) amount")
```

- [ ] **Step 4: Unguard _validate_calloff_po call sites**

The three call sites (lines 482, 576, 681) guard `_validate_calloff_po` with `if calloff_po_id is not None:`. This means `request_type == "call_off"` + no `calloff_po_id` bypasses validation. Since the new function handles all cases internally, remove the guard at all three call sites:

**create_sc** (line 455-483): Remove the separate FC check at lines 455-456:
```python
calloff_po_id = data.get("calloff_po_id")
if calloff_po_id is not None and data["request_type"] == "FC":
    raise ValidationError("FC request_type cannot have calloff_po_id")
```
And change line 482-483 from:
```python
if calloff_po_id is not None:
    _validate_calloff_po(conn, calloff_po_id, data["request_type"], sc_amount)
```
to:
```python
_validate_calloff_po(conn, calloff_po_id, data["request_type"], sc_amount)
```

**create_sc_draft** (line 575-577): Change from:
```python
calloff_po_id = data.get("calloff_po_id")
if calloff_po_id is not None:
    _validate_calloff_po(conn, calloff_po_id, data.get("request_type"), data.get("sc_amount"))
```
to:
```python
calloff_po_id = data.get("calloff_po_id")
_validate_calloff_po(conn, calloff_po_id, data.get("request_type"), data.get("sc_amount"))
```

**submit_sc** (line 680-682): Change from:
```python
calloff_po_id = before.get("calloff_po_id")
if calloff_po_id is not None:
    _validate_calloff_po(conn, calloff_po_id, merged.get("request_type"), merged["sc_amount"], exclude_sc_id=sc_id)
```
to:
```python
calloff_po_id = before.get("calloff_po_id")
_validate_calloff_po(conn, calloff_po_id, merged.get("request_type"), merged["sc_amount"], exclude_sc_id=sc_id)
```

- [ ] **Step 5: Run SC service tests to verify validation**

```bash
cd c:/Users/V2SE7PP/Projects/contract && python -m pytest tests/test_sc_service.py -v
```

Expected: Tests using new `SUPPORTED_REQUEST_TYPES` values will fail (update in Task 12). Tests for FC flow should still work.

- [ ] **Step 6: Commit**

```bash
git add sc_gr_app/services/sc_service.py
git commit -m "feat: remap request_type to FC/call_off/new, add service_scope to SC CRUD"
```

---

### Task 4: Backend — Update SC import/export for request_type and service_scope

**Files:**
- Modify: `sc_gr_app/services/import_service.py:14-31` (add service_scope alias)
- Modify: `sc_gr_app/services/import_service.py:184-235` (_validate_sc_rows add request_type validation)
- Modify: `sc_gr_app/services/export_service.py:448` (SC export column mapping)

- [ ] **Step 1: Add service_scope to SC column aliases**

In `_SC_COLUMN_ALIASES` (after line 30, before the closing `}`), add:

```python
"service_scope":          ["Service Scope", "service_scope", "服务范围"],
```

- [ ] **Step 2: Add request_type validation in _validate_sc_rows**

After the status validation (line 196), add request_type validation:

```python
# Validate request_type
rt = str(row.get("request_type", "")).strip()
if rt and rt not in ("FC", "call_off", "new"):
    errors.append({"row": i, "field": "request_type", "message": f"Invalid request_type: {rt}"})
```

After the `calloff_po_id` validation (line 211), add service_scope validation:

```python
# Validate service_scope if provided
scope = str(row.get("service_scope", "")).strip()
if scope:
    from sc_gr_app.services.vendor_service import SUPPORTED_SERVICE_SCOPES
    if scope not in SUPPORTED_SERVICE_SCOPES:
        errors.append({"row": i, "field": "service_scope", "message": f"Invalid service_scope: {scope}"})
```

- [ ] **Step 3: Add service_scope to import_scs INSERT**

The SC import INSERT at lines 274-299 does NOT include `service_scope`. Add it after `currency` and before `internal_system_number` in both the column list and VALUES:

**Column list** (line 277): Add `service_scope,` after `currency,`:
```python
status, description, currency, service_scope, internal_system_number,
```

**VALUES** (line 280): Change `(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)` to `(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)` (add 19th `?`).

**Params tuple** (line 293-298): Add `row.get("service_scope"),` after `row.get("currency", "CNY"),`:
```python
row.get("currency", "CNY"),
row.get("service_scope"),
row.get("internal_system_number"),
```

- [ ] **Step 4: Add service_scope to SC export filter whitelist**

At `sc_gr_app/services/export_service.py` line 448, the `_build_where` function has an `allowed` dict for filter fields. Add `"service_scope"` to the `"sc_records"` entry so export filtering works for this field:

```python
"sc_records": {"status": "status", "requester_id": "requester_id", "sc_no": "sc_no",
               "request_type": "request_type", "cost_center": "cost_center",
               "service_scope": "service_scope"},
```

The actual column is selected via `SELECT sc.* FROM sc_records` and will be included automatically since the DB table now has the column. The frontend ExportDialog.vue (Task 13) handles the UI field definition.

- [ ] **Step 5: Run import/export tests**

```bash
cd c:/Users/V2SE7PP/Projects/contract && python -m pytest tests/test_import_service.py tests/test_export_service.py -v
```

Expected: Existing tests may fail on request_type values. That will be handled in Task 12.

- [ ] **Step 6: Commit**

```bash
git add sc_gr_app/services/import_service.py sc_gr_app/services/export_service.py
git commit -m "feat: add service_scope to SC import/export, validate request_type on import"
```

---

### Task 5: Backend — Update query_service.py for service_scope

**Files:**
- Modify: `sc_gr_app/services/query_service.py:325-366` (search_scs search/filter/sort fields)

- [ ] **Step 1: Add service_scope to search_scs**

In the `search_scs` function (line 185), add `"service_scope"` to four locations:

**text_columns** (line 220-239): Add `"sc.service_scope",` after `"sc.description",`:
```python
"sc.description",
"sc.service_scope",
"sc.request_type",
```

**allowed_filters** (line 241-254): Add `"service_scope": "sc.service_scope",` after `"request_type"`:
```python
"request_type": "sc.request_type",
"service_scope": "sc.service_scope",
"cost_center": "sc.cost_center",
```

**allowed_sorts** (read the same section around line 255-270): Add `"service_scope": "sc.service_scope",` in the sorts dict.

**like_fields** (search for `like_fields` in the `_search` call within `search_scs`): Add `"service_scope"` to the set. If there is no `like_fields` parameter, the `_search` function uses `text_columns` for LIKE matching — verify by reading the `_search` function signature. If text_columns handles it, no additional change is needed.

- [ ] **Step 2: Run query service tests**

```bash
cd c:/Users/V2SE7PP/Projects/contract && python -m pytest tests/test_query_service.py -v
```

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/services/query_service.py
git commit -m "feat: add service_scope to SC search/filter/sort"
```

---

### Task 6: Backend — Update bridge.py SC template

**Files:**
- Modify: `sc_gr_app/api/bridge.py:1909-1925` (download_sc_template)

- [ ] **Step 1: Update template headers, hints, and sample row**

At line 1909 (headers), add `"service_scope"` between `"currency"` and `"internal_system_number"`:

```python
headers = ["sc_no", "vendor_id", "requester_id", "request_type", "cost_center",
           "sc_amount", "service_period_start", "service_period_end", "status",
           "description", "currency", "service_scope", "internal_system_number", "calloff_po_id",
           "asset", "asset_nums"]
```

At line 1916 (hints), change `"material/service/fixed_asset/FC"` to `"FC/call_off/new"` and add a hint for service_scope between `"CNY/EUR/USD"` and `"Optional (FC only)"`:

```python
hints = ["Required (business NO, must be unique)",
         "Optional (comma-separated, e.g. V000001,V000002)",
         "Optional (defaults to importer)",
         "FC/call_off/new", "Cost center number",
         "Required (e.g. 50000)", "YYYY-MM-DD or MM/DD/YYYY", "YYYY-MM-DD or MM/DD/YYYY",
         "approved/finished", "Optional",
         "CNY/EUR/USD", "Optional (see service scope list)",
         "Optional (FC only)",
         "Optional (FC call-off only)",
         "Y/N (default N)", "Optional"]
```

At line 1922 (sample row), change `"material"` to `"new"` and add empty string for service_scope between `"CNY"` and `""` (the internal_system_number placeholder):

```python
sample = ["[EXAMPLE]", "", current_user["user_id"], "new", "12345",
          "50000", "2026-01-01", "2026-12-31", "approved",
          "Sample SC description", "CNY", "", "", "",
          "N", ""]
```

- [ ] **Step 2: Verify template download works**

```bash
cd c:/Users/V2SE7PP/Projects/contract && python -c "
from sc_gr_app.api.bridge import Bridge
# Check function syntax is valid
print('OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/api/bridge.py
git commit -m "feat: update SC template with new request_type values and service_scope"
```

---

### Task 7: Backend — Update notification email template for request_type display

**Files:**
- Modify: `sc_gr_app/notification/templates.py:243-290` (_entity_detail_rows)

- [ ] **Step 1: Add _REQUEST_TYPE_LABEL constant**

After `_STATUS_LABELS` (around line 60), add:

```python
_REQUEST_TYPE_LABELS: dict[str, str] = {
    "FC": "FC",
    "call_off": "Call Off",
    "new": "",
}
```

- [ ] **Step 2: Apply label mapping in _entity_detail_rows**

After line 277 (`val = _STATUS_LABELS.get(val, val)`), add an elif for request_type:

```python
elif key == "request_type":
    val = _REQUEST_TYPE_LABELS.get(val, val)
```

Also add the same block in the second loop (after line 289, inside the `for key, value` loop where status is handled):

```python
elif key == "request_type":
    value = _REQUEST_TYPE_LABELS.get(value, value)
```

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/notification/templates.py
git commit -m "feat: add request_type display label mapping for email templates"
```

---

### Task 8: Seed data update

**Files:**
- Modify: `seed_data.py:46,52,55` (vendor service_scope old values)
- Modify: `seed_data.py:110,116,122,135` (SC request_type old values)

- [ ] **Step 1: Update vendor service_scope values**

Lines 46, 52, 55: Change `"engineering Service"` → `"Engineering Service"`:

```python
# Line 46
"contact_person": "Zhang Wei", "phone": "13800001001", "service_scope": "Engineering Service",
# Line 52
"contact_person": "Wang Fang", "phone": "13800001003", "service_scope": "Engineering Service",
# Line 55
"contact_person": "Chen Jie", "phone": "13800001004", "service_scope": "Engineering Service",
```

- [ ] **Step 2: Update SC request_type values**

Lines 110, 116, 122, 135: Change `"service"` / `"material"` / `"fixed_asset"` → `"new"`:

```python
# Line 110
submit(client, cookies, sc_ids["SC-2"], machine_id, "service", cost_center, amount, start, end)
# → change "service" to "new"
submit(client, cookies, sc_ids["SC-2"], machine_id, "new", cost_center, amount, start, end)
```

Similarly update lines 116 (`"material"`), 122 (`"service"`), 135 (`"fixed_asset"`) all to `"new"`.

- [ ] **Step 3: Verify seed data syntax**

```bash
cd c:/Users/V2SE7PP/Projects/contract && python -c "import ast; ast.parse(open('seed_data.py').read()); print('Syntax OK')"
```

- [ ] **Step 4: Commit**

```bash
git add seed_data.py
git commit -m "chore: update seed data for new service_scope and request_type values"
```

---

### Task 9: Frontend — Add shared requestTypeLabel utility

**Files:**
- Create: `frontend/src/composables/useRequestType.js`

- [ ] **Step 1: Create the composable file**

```javascript
export function requestTypeLabel(type) {
  if (!type) return ''
  const map = { FC: 'FC', call_off: 'Call Off', new: '' }
  return map[type] || type
}

export function requestTypeAbbr(type) {
  if (!type) return ''
  const map = { FC: 'FC', call_off: 'CO', new: '' }
  return map[type] || type
}
```

- [ ] **Step 2: Verify file syntax**

```bash
cd c:/Users/V2SE7PP/Projects/contract && node -e "import('./frontend/src/composables/useRequestType.js').then(m => console.log(Object.keys(m)))" 2>&1 || echo "Check manually in browser"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/composables/useRequestType.js
git commit -m "feat: add shared requestTypeLabel utility composable"
```

---

### Task 10: Frontend — Update ScFormDialog.vue (request_type + service_scope)

**Files:**
- Modify: `frontend/src/components/sc/ScFormDialog.vue:31-33` (request_type dropdown)
- Modify: `frontend/src/components/sc/ScFormDialog.vue:173-177` (requestTypes computed)
- Add: service_scope form field in template and script

- [ ] **Step 1: Update requestTypes computed**

Line 173-177, replace:

```javascript
const requestTypes = computed(() => {
  const types = ['material', 'service', 'fixed_asset', 'FC']
  if (props.calloffPoId) return types.filter(t => t !== 'FC')
  return types
})
```

with:

```javascript
import { requestTypeLabel } from '@/composables/useRequestType.js'

const requestTypes = computed(() => {
  const types = ['FC', 'call_off', 'new']
  if (props.calloffPoId) return types.filter(t => t !== 'FC')
  return types
})
```

- [ ] **Step 2: Update request_type el-option to use label**

Line 33, change:
```html
<el-option v-for="t in requestTypes" :key="t" :label="t" :value="t" />
```
to:
```html
<el-option v-for="t in requestTypes" :key="t" :label="requestTypeLabel(t) || t" :value="t" />
```

- [ ] **Step 3: Add service_scope field to template**

After the `request_type` el-form-item (around line 34), add:

```html
<el-form-item :label="$t('vendor.serviceScope')">
  <el-select v-model="form.service_scope" clearable :placeholder="$t('common.optional')">
    <el-option v-for="s in serviceScopes" :key="s" :label="s" :value="s" />
  </el-select>
</el-form-item>
```

- [ ] **Step 4: Add serviceScopes array and form field**

In the script section, import `SUPPORTED_SERVICE_SCOPES` equivalent or define the array. Since the frontend doesn't import from Python, hardcode the shared list:

After `const requestTypes = computed(...)`:

```javascript
const serviceScopes = [
  'Transportation', 'Engineering Service', 'Equipment', 'Parts', 'Driver',
  'Test car rental', 'General Service', 'Dealers', 'Import&Export&cusoms clearance',
  'Insurance', 'Harness', 'Maintenance&Calibration', 'Security', 'Testing support', 'Others'
]
```

In `emptyForm()` (line 182), add `service_scope: ''` to the returned object.

- [ ] **Step 5: IF calloffPoId prop is set, auto-set request_type to call_off**

In the `watch` for `props.visible` (around line 117), add logic: when `calloffPoId` is provided, auto-set `form.request_type = 'call_off'`:

After the existing `Object.assign(form, props.record)` line in the edit branch, and after `Object.assign(form, emptyForm())` in the create branch, check:

```javascript
if (props.calloffPoId) {
  form.request_type = 'call_off'
}
```

- [ ] **Step 6: Verify the frontend builds**

Check syntax by reading the file — no backend build step needed.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/sc/ScFormDialog.vue
git commit -m "feat: update ScFormDialog with new request_type values and service_scope field"
```

---

### Task 11: Frontend — Update ScListView, ScDetailCard, ScTable, HomeView

**Files:**
- Modify: `frontend/src/views/ScListView.vue:139` (requestTypes)
- Modify: `frontend/src/views/ScListView.vue:222` (filter config)
- Modify: `frontend/src/views/HomeView.vue:312-316` (typeLabel)
- Modify: `frontend/src/components/sc/ScDetailCard.vue` (add service_scope display)
- Modify: `frontend/src/components/sc/ScTable.vue` (add service_scope column)

- [ ] **Step 1: Update ScListView requestTypes and filter**

At line 139, change:
```javascript
const requestTypes = ['material', 'service', 'fixed_asset', 'FC']
```
to:
```javascript
const requestTypes = ['FC', 'call_off', 'new']
```

At line 222 (filter config), update the options to use `requestTypeLabel`:
```javascript
{ name: 'request_type', label: t('filter.requestType'), type: 'select',
  options: requestTypes.map(t => ({ label: requestTypeLabel(t) || t, value: t })) },
```

Add import at top of `<script setup>`:
```javascript
import { requestTypeLabel } from '@/composables/useRequestType.js'
```

Add service_scope filter:
```javascript
{ name: 'service_scope', label: t('vendor.serviceScope'), type: 'select',
  options: serviceScopes.map(s => ({ label: s, value: s })) },
```

Also add `serviceScopes` array (same as in Task 10).

- [ ] **Step 2: Update HomeView typeLabel**

At line 312-316, replace:
```javascript
function typeLabel(requestType) {
  if (!requestType) return '-'
  const map = { material: 'M', service: 'S', fixed_asset: 'FA', FC: 'FC' }
  return map[requestType] || requestType
}
```
with:
```javascript
import { requestTypeAbbr } from '@/composables/useRequestType.js'

function typeLabel(requestType) {
  if (!requestType) return '-'
  return requestTypeAbbr(requestType) || '-'
}
```

- [ ] **Step 3: Add service_scope to ScDetailCard**

After the `request_type` el-descriptions-item (line 6), add:

```html
<el-descriptions-item v-if="sc.service_scope" :label="$t('vendor.serviceScope')">
  {{ sc.service_scope }}
</el-descriptions-item>
```

- [ ] **Step 4: Add service_scope column to ScTable**

After the `request_type` column (line 32), add:

```html
<el-table-column prop="service_scope" :label="$t('vendor.serviceScope')" width="150">
  <template #default="{ row }">
    <span>{{ row.service_scope || '-' }}</span>
  </template>
</el-table-column>
```

- [ ] **Step 5: Update ScTable request_type cell to use label**

Change the raw `{{ row.request_type }}` to use the label function:
```html
<span>{{ requestTypeLabel(row.request_type) || '-' }}</span>
```

Add import:
```javascript
import { requestTypeLabel } from '@/composables/useRequestType.js'
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/ScListView.vue frontend/src/views/HomeView.vue frontend/src/components/sc/ScDetailCard.vue frontend/src/components/sc/ScTable.vue
git commit -m "feat: update SC views with new request_type labels and service_scope display"
```

---

### Task 12: Frontend — Update VendorFormDialog.vue serviceScopes

**Files:**
- Modify: `frontend/src/components/vendor/VendorFormDialog.vue:98-101` (serviceScopes array)

- [ ] **Step 1: Update serviceScopes array**

Lines 98-101, replace:

```javascript
const serviceScopes = [
  'Transportation', 'engineering Service', 'Equipment', 'Parts', 'Driver',
  'Test car rental', 'General Service', 'Dealers', 'Import&Export&cusoms clearance',
  'Insurance', 'Harness', 'Maintenance', 'Security', 'Testing support', 'Others'
]
```

with:

```javascript
const serviceScopes = [
  'Transportation', 'Engineering Service', 'Equipment', 'Parts', 'Driver',
  'Test car rental', 'General Service', 'Dealers', 'Import&Export&cusoms clearance',
  'Insurance', 'Harness', 'Maintenance&Calibration', 'Security', 'Testing support', 'Others'
]
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/vendor/VendorFormDialog.vue
git commit -m "fix: update VendorFormDialog service_scope dropdown options"
```

---

### Task 13: Frontend — Update ExportDialog.vue

**Files:**
- Modify: `frontend/src/components/export/ExportDialog.vue` (SC field definitions)

- [ ] **Step 1: Add service_scope to SC export fields**

Find the SC field definitions (around line 139 where `{ key: 'request_type', label: t('export.type') }` appears) and add:

```javascript
{ key: 'service_scope', label: t('vendor.serviceScope') },
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/export/ExportDialog.vue
git commit -m "feat: add service_scope to SC export dialog"
```

---

### Task 14: Tests — Update all test files for new request_type and service_scope values

**Files:**
- Modify: `tests/conftest.py:37` (fixture request_type)
- Modify: `tests/test_sc_service.py` (SUPPORTED_REQUEST_TYPES test, request_type values in payloads)
- Modify: `tests/test_po_service.py` (request_type values in PO payloads)
- Modify: `tests/test_gr_service.py` (request_type values)
- Modify: `tests/test_fc_calloff_flow.py` (request_type values in FC/call-off tests)
- Modify: `tests/test_sc_po_gr_flow.py` (request_type values)
- Modify: `tests/test_query_service.py` (request_type filter values)
- Modify: `tests/test_budget_service.py` (request_type values)
- Modify: `tests/test_export_service.py` (request_type values)
- Modify: `tests/test_import_service.py` (request_type + service_scope values)
- Modify: `tests/test_migrations.py` (v35 assertions)
- Modify: `tests/test_sc_vendor_snapshot.py` (request_type values)
- Modify: `tests/test_api.py` (request_type values)
- Modify: `tests/web_sc_detail_state.test.mjs` (request_type expected value)

- [ ] **Step 1: Update conftest.py fixture**

At line 37, change `'request_type': 'service'` → `'request_type': 'new'`.

- [ ] **Step 2: Update test_sc_service.py**

- Line 47-52 (`test_create_sc_rejects_invalid_request_type`): Change the invalid value used from e.g. `"invalid"` to validate against `SUPPORTED_REQUEST_TYPES`. The test should still pass with any value not in `{"FC", "call_off", "new"}` — verify the specific value used.
- Replace all `"request_type": "material"` → `"request_type": "new"` in test payloads.
- Replace `"request_type": "service"` → `"request_type": "new"`.
- `"request_type": "FC"` stays.

Run a find-and-replace for the file. Pattern: search for `"material"`, `"service"`, `"fixed_asset"` in context of `request_type` and replace with `"new"`.

- [ ] **Step 3: Update remaining Python test files**

For each test file, replace old request_type values:
- `"request_type": "material"` → `"request_type": "new"`
- `"request_type": "service"` → `"request_type": "new"`
- `"request_type": "fixed_asset"` → `"request_type": "new"`
- `"request_type": "FC"` → unchanged
- `request_type = 'material'` → `request_type = 'new'` (in SQL INSERT statements)
- `request_type = 'service'` → `request_type = 'new'`
- `request_type = 'fixed_asset'` → `request_type = 'new'`

Files to update:
- `tests/test_po_service.py`
- `tests/test_gr_service.py`
- `tests/test_fc_calloff_flow.py`
- `tests/test_sc_po_gr_flow.py`
- `tests/test_query_service.py`
- `tests/test_budget_service.py`
- `tests/test_export_service.py`
- `tests/test_import_service.py`
- `tests/test_sc_vendor_snapshot.py`
- `tests/test_api.py`
- `tests/test_id_generation.py` (if any)
- `tests/test_notification_bridge.py` (if any)
- `tests/test_notification_thresholds.py` (if any)

- [ ] **Step 4: Add v35 migration test**

In `tests/test_migrations.py`, add a test for v35. Follow the existing pattern (e.g., `test_migration_v34`):

```python
def test_migration_v35(fresh_db, app_config):
    """v35: remaps request_type, renames service_scope values, adds service_scope column."""
    conn = fresh_db
    # Seed old-style data
    conn.execute(
        "INSERT INTO users (user_id, machine_id, user_name, role, created_at, updated_at) "
        "VALUES ('U1', 'M1', 'Test', 'admin', '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at) "
        "VALUES ('V1', 'Test Vendor', 'engineering Service', 'U1', '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at) "
        "VALUES ('V2', 'Test Vendor 2', 'Maintenance', 'U1', '2026-01-01', '2026-01-01')"
    )

    from sc_gr_app.db.migrations import _migrate_v35, _record
    # Manually set version
    conn.execute("DELETE FROM schema_migrations WHERE version = 35")
    _migrate_v35(conn)

    # Verify vendor service_scope renamed
    row = conn.execute("SELECT service_scope FROM vendors WHERE vendor_id = 'V1'").fetchone()
    assert row["service_scope"] == "Engineering Service"
    row = conn.execute("SELECT service_scope FROM vendors WHERE vendor_id = 'V2'").fetchone()
    assert row["service_scope"] == "Maintenance&Calibration"

    # Verify service_scope column exists on sc_records
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(sc_records)")}
    assert "service_scope" in cols
```

- [ ] **Step 5: Update frontend test**

In `tests/web_sc_detail_state.test.mjs`, change expected `request_type` value from `"service"` to `"new"` or update the test data accordingly.

- [ ] **Step 6: Run full test suite**

```bash
cd c:/Users/V2SE7PP/Projects/contract && python -m pytest tests/ -v --tb=short
```

Expected: All tests pass after the value replacements. Fix any remaining failures.

- [ ] **Step 7: Commit**

```bash
git add tests/
git commit -m "test: update tests for new request_type values, service_scope, and v35 migration"
```

---

### Task 15: Integration verification

**Files:**
- (verification only, no file changes)

- [ ] **Step 1: Start the app and run seed data**

```bash
cd c:/Users/V2SE7PP/Projects/contract && python seed_data.py --force
```

Expected: Seed data creates successfully with new values. No migration or validation errors.

- [ ] **Step 2: Manual smoke test checklist**

- [ ] Create a new SC with request_type `FC` — verify it saves and displays correctly
- [ ] Create a new SC with request_type `new` — verify no request_type label shown
- [ ] Create a new SC with request_type `call_off` — verify parent PO selection flow works
- [ ] Edit an existing SC (migrated old value) — verify request_type shows correctly
- [ ] Create a new vendor — verify service_scope dropdown shows new values
- [ ] Import vendors via CSV — verify old service_scope values are rejected
- [ ] Import SCs via CSV — verify old request_type values are rejected
- [ ] Export SCs — verify service_scope column included
- [ ] Send notification email — verify request_type displays as "Call Off" / "FC" / blank
- [ ] Check HomeView workbench — verify `typeLabel` shows FC/CO/blank for new values

- [ ] **Step 3: Commit any final fixes**

```bash
git status
git add -A
git commit -m "chore: integration fixes for request_type and service_scope changes"
```
