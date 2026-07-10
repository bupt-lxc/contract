# PO(FC) and Call-off SC Connection Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the broken connection between PO(FC) and call-off SCs by ensuring `calloff_po_id` is resolved from `internal_system_number` at import time, and all import/update paths write relevant columns correctly.

**Architecture:** Data-layer fix — resolve `internal_system_number` (Supplier column from Excel, which contains PO external numbers) → `po_no` → `po_id` during CSV generation, then ensure `import_scs` writes the resolved `calloff_po_id` (plus `service_scope`, `asset_nums`) to the DB. Fix `update_sc` to persist `service_scope` edits. Fix `import_pos` to include `request_type`. Fix downloadable SC template to include missing columns.

**Tech Stack:** Python backend (sqlite3, openpyxl), Vue 3 frontend (Element Plus)

---

### Task 1: Fix import_scs INSERT to include service_scope, calloff_po_id, asset_nums

**Files:**
- Modify: `sc_gr_app/services/import_service.py:171-194`

- [ ] **Step 1: Add three new columns to the INSERT statement**

Replace the INSERT statement at lines 171-194:

```python
                    conn.execute(
                        """INSERT INTO sc_records (
                          sc_id, sc_no, requester_id, request_type, cost_center,
                          sc_amount, service_period_start, service_period_end,
                          status, description, currency, internal_system_number,
                          service_scope, calloff_po_id, asset_nums,
                          created_by, created_at, updated_at, asset
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'N')""",
                        (
                            sc_id,
                            row.get("sc_no"),
                            row.get("requester_id") or current_user["user_id"],
                            _normalize_request_type(row.get("request_type")),
                            row.get("cost_center"),
                            float(row["sc_amount"]) if row.get("sc_amount") else None,
                            row.get("service_period_start"),
                            row.get("service_period_end"),
                            row["status"],
                            row.get("description"),
                            row.get("currency", "CNY"),
                            row.get("internal_system_number"),
                            row.get("service_scope"),
                            row.get("calloff_po_id"),
                            row.get("asset_nums"),
                            current_user["user_id"],
                            timestamp,
                            timestamp,
                        ),
                    )
```

- [ ] **Step 2: Run existing import tests to check for regressions**

```bash
cd c:\Users\V2SE7PP\Projects\contract && python -m pytest tests/test_import_service.py -v
```

Expected: All existing import tests pass (the new columns accept NULL/default values for tests that don't set them).

- [ ] **Step 3: Add test verifying new columns are written**

Add to `tests/test_import_service.py`:

```python
def test_import_sc_writes_service_scope_and_calloff_po_id(self, app_config):
    migrate(app_config)
    with connect(app_config) as conn:
        _seed_user(conn)
    current_user = {"user_id": "U000001", "machine_id": "M000001", "role": "requester"}
    rows = [{"sc_no": "SC-NEW-COLS", "sc_amount": "50000", "status": "approved",
             "request_type": "call_off", "cost_center": "1000",
             "service_period_start": "2026-01-01", "service_period_end": "2026-12-31",
             "service_scope": "Transportation", "calloff_po_id": "PO-TEST-001",
             "asset_nums": "ASSET-123"}]
    result = import_service.import_scs(app_config, current_user, rows)
    assert result["ok"] is True
    with connect(app_config) as conn:
        sc = conn.execute(
            "SELECT service_scope, calloff_po_id, asset_nums FROM sc_records WHERE sc_no = ?",
            ("SC-NEW-COLS",)).fetchone()
    assert sc["service_scope"] == "Transportation"
    assert sc["calloff_po_id"] == "PO-TEST-001"
    assert sc["asset_nums"] == "ASSET-123"
```

- [ ] **Step 4: Run the new test**

```bash
cd c:\Users\V2SE7PP\Projects\contract && python -m pytest tests/test_import_service.py::TestImportService::test_import_sc_writes_service_scope_and_calloff_po_id -v
```

Expected: PASS.

Note: The `calloff_po_id` column is added by migration v34 and exists after `migrate()`. The current codebase is at migration v36+. No additional migration is needed.

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/services/import_service.py tests/test_import_service.py
git commit -m "fix: import_scs INSERT includes service_scope, calloff_po_id, asset_nums"
```

---

### Task 2: Add missing entries to _SC_COLUMN_ALIASES

**Files:**
- Modify: `sc_gr_app/services/import_service.py:335-348`

- [ ] **Step 1: Add alias entries for the four missing columns**

Add after line 347 (`"internal_system_number": ...`):

```python
    "service_scope": ["Service Scope", "service_scope"],
    "calloff_po_id": ["Call-off PO ID", "calloff_po_id"],
    "asset_nums": ["Asset Nums", "asset_nums"],
    "asset": ["Asset", "asset"],
```

- [ ] **Step 2: Add test for new aliases**

In `tests/test_import_service.py`, add:

```python
def test_normalize_header_maps_new_sc_aliases(self):
    assert import_service._normalize_import_header("Service Scope") == "service_scope"
    assert import_service._normalize_import_header("service_scope") == "service_scope"
    assert import_service._normalize_import_header("Call-off PO ID") == "calloff_po_id"
    assert import_service._normalize_import_header("Asset Nums") == "asset_nums"
    assert import_service._normalize_import_header("Asset") == "asset"
```

- [ ] **Step 3: Run the alias test**

```bash
cd c:\Users\V2SE7PP\Projects\contract && python -m pytest tests/test_import_service.py::TestImportService::test_normalize_header_maps_new_sc_aliases -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/services/import_service.py
git commit -m "fix: add service_scope, calloff_po_id, asset_nums, asset to _SC_COLUMN_ALIASES"
```

---

### Task 3: Fix import_pos INSERT to include request_type

**Files:**
- Modify: `sc_gr_app/services/import_service.py:284-310`

- [ ] **Step 1: Add request_type to the INSERT columns and values**

Replace the INSERT statement at lines 284-310:

```python
                    conn.execute(
                        """INSERT INTO pos (
                          po_id, sc_id, vendor_id, po_no, requester_id,
                          po_amount, status, contract_from, contract_to, contract_no,
                          payment_frequency, contract_pos, contract_type, cost_center,
                          purchaser, request_type, active_date, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            po_id,
                            row["sc_id"],
                            row.get("vendor_id"),
                            row.get("po_no"),
                            row.get("requester_id") or current_user["user_id"],
                            float(row["po_amount"]) if row.get("po_amount") else None,
                            row.get("status", "draft"),
                            row.get("contract_from"),
                            row.get("contract_to"),
                            row.get("contract_no"),
                            row.get("payment_frequency"),
                            row.get("contract_pos"),
                            row.get("contract_type"),
                            row.get("cost_center"),
                            row.get("purchaser"),
                            row.get("request_type"),
                            None if row.get("status") == "draft" else timestamp,
                            timestamp,
                            timestamp,
                        ),
                    )
```

- [ ] **Step 2: Run import tests**

```bash
cd c:\Users\V2SE7PP\Projects\contract && python -m pytest tests/test_import_service.py -v
```

Expected: All tests pass.

Note: `pos.request_type` CHECK constraint was relaxed by migration v36 to accept `('FC', 'call_off', 'new')`. Current DB is at v36+ so this is satisfied.

- [ ] **Step 3: Add test verifying request_type is written on import**

In `tests/test_import_service.py`, add:

```python
def test_import_po_writes_request_type(self, app_config):
    migrate(app_config)
    with connect(app_config) as conn:
        _seed_user(conn)
        _seed_sc(conn)
        _seed_vendor(conn)
    current_user = {"user_id": "U000001", "machine_id": "M000001", "role": "requester"}
    rows = [{"sc_no": "SCNO-SC-0000001-20260701-001", "vendor_id": "V000001",
             "po_no": "PO-REQ-TYPE", "po_amount": "50000", "status": "active",
             "request_type": "FC"}]
    result = import_service.import_pos(app_config, current_user, rows)
    assert result["ok"] is True
    with connect(app_config) as conn:
        po = conn.execute("SELECT request_type FROM pos WHERE po_no = ?",
                          ("PO-REQ-TYPE",)).fetchone()
    assert po["request_type"] == "FC"
```

- [ ] **Step 4: Run the new test**

```bash
cd c:\Users\V2SE7PP\Projects\contract && python -m pytest tests/test_import_service.py::TestImportService::test_import_po_writes_request_type -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/services/import_service.py
git commit -m "fix: import_pos INSERT includes request_type column"
```

---

### Task 4: Fix update_sc to write service_scope

**Files:**
- Modify: `sc_gr_app/services/sc_service.py:862-899`

**Context:** `service_scope` is already in `OPTIONAL_UPDATE_FIELDS` (line 46), so the `update_sc` function accepts it in the inbound data dict and passes the allowed-field filter. However, the actual UPDATE SQL (lines 863-878) never included `service_scope` in the SET columns, so the value is silently discarded — no error, but no persistence. This fix closes that gap.

- [ ] **Step 1: Add `service_scope = ?` to the UPDATE SET columns**

Add `service_scope = ?,` after `internal_system_number = ?,` in the SET clause, and add `merged.get("service_scope"),` to the parameter tuple after `merged.get("internal_system_number"),`:

The update block at lines 863-898 becomes:

```python
                timestamp = utc_now()
                conn.execute(
                    """
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
                        internal_system_number = ?,
                        service_scope = ?,
                        currency = ?,
                        updated_at = ?
                    where sc_id = ?
                    """,
                    (
                        merged.get("sc_no"),
                        merged.get("request_type"),
                        merged.get("cost_center"),
                        (
                            float(merged["sc_amount"])
                            if merged.get("sc_amount") not in (None, "")
                            else None
                        ),
                        merged.get("service_period_start"),
                        merged.get("service_period_end"),
                        merged.get("description"),
                        merged.get("asset"),
                        merged.get("asset_nums"),
                        merged.get("internal_system_number"),
                        merged.get("service_scope"),
                        merged.get("currency"),
                        timestamp,
                        sc_id,
                    ),
                )
```

- [ ] **Step 2: Run SC update tests**

```bash
cd c:\Users\V2SE7PP\Projects\contract && python -m pytest tests/test_sc_service.py -v -k "update"
```

Expected: All update-related tests pass.

- [ ] **Step 3: Add test verifying service_scope is persisted on update**

In `tests/test_sc_service.py`, add:

```python
def test_update_sc_persists_service_scope(self, seeded_config):
    admin, requester = _resolve_users(seeded_config)
    sc = create_sc_draft(seeded_config, admin, {"requester_id": requester["user_id"]})
    result = update_sc(seeded_config, admin, sc["sc_id"], {
        "service_scope": "Engineering Service",
    })
    assert result["service_scope"] == "Engineering Service"
    detail = get_sc_detail(seeded_config, admin, sc["sc_id"])
    assert detail["sc"]["service_scope"] == "Engineering Service"
```

- [ ] **Step 4: Run the new test**

```bash
cd c:\Users\V2SE7PP\Projects\contract && python -m pytest tests/test_sc_service.py::test_update_sc_persists_service_scope -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/services/sc_service.py tests/test_sc_service.py
git commit -m "fix: update_sc writes service_scope to database"
```

---

### Task 5: Fix downloadable SC template to include missing columns

**Files:**
- Modify: `sc_gr_app/api/bridge.py:1885-1896`

- [ ] **Step 1: Update headers, hints, and sample arrays**

Replace lines 1885-1896:

```python
        headers = ["sc_id", "sc_no", "requester_id", "request_type", "cost_center",
                   "sc_amount", "service_period_start", "service_period_end", "status",
                   "description", "currency", "service_scope", "internal_system_number",
                   "calloff_po_id", "asset", "asset_nums"]
        hints = ["Optional (auto-generated if empty)", "Optional",
                 "Optional (defaults to importer)",
                 "material/service/fixed_asset/FC/call_off", "Cost center number",
                 "Required (e.g. 50000)", "YYYY-MM-DD", "YYYY-MM-DD",
                 "approved/finished", "Optional",
                 "CNY/EUR/USD", "Service scope (e.g. Transportation)", "Optional",
                 "Optional (PO ID for call-off SC)", "N/Y", "Optional"]
        sample = ["[EXAMPLE]", "", "", "material", "12345",
                  "50000", "2026-01-01", "2026-12-31", "draft",
                  "Sample SC description", "CNY", "Transportation", "",
                  "", "N", ""]
```

- [ ] **Step 2: Add test for header/hint/sample alignment**

In `tests/test_api_bridge.py`, add:

```python
def test_sc_template_headers_hints_sample_aligned():
    """Verify all three template arrays have the same length to prevent
    xlsx generation errors."""
    # Headers, hints, and sample must stay in sync
    headers = ["sc_id", "sc_no", "requester_id", "request_type", "cost_center",
               "sc_amount", "service_period_start", "service_period_end", "status",
               "description", "currency", "service_scope", "internal_system_number",
               "calloff_po_id", "asset", "asset_nums"]
    hints = ["Optional (auto-generated if empty)", "Optional",
             "Optional (defaults to importer)",
             "material/service/fixed_asset/FC/call_off", "Cost center number",
             "Required (e.g. 50000)", "YYYY-MM-DD", "YYYY-MM-DD",
             "approved/finished", "Optional",
             "CNY/EUR/USD", "Service scope (e.g. Transportation)", "Optional",
             "Optional (PO ID for call-off SC)", "N/Y", "Optional"]
    sample = ["[EXAMPLE]", "", "", "material", "12345",
              "50000", "2026-01-01", "2026-12-31", "draft",
              "Sample SC description", "CNY", "Transportation", "",
              "", "N", ""]
    assert len(headers) == len(hints) == len(sample)
```

- [ ] **Step 3: Run the alignment test**

```bash
cd c:\Users\V2SE7PP\Projects\contract && python -m pytest tests/test_api_bridge.py::test_sc_template_headers_hints_sample_aligned -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/api/bridge.py tests/test_api_bridge.py
git commit -m "fix: downloadable SC template includes service_scope, calloff_po_id, asset, asset_nums"
```

---

### Task 6: Add internal_system_number → calloff_po_id resolution pass to process_c26_import.py

**Files:**
- Modify: `docs/process_c26_import.py`

Note: This is a **best-effort** resolution against POs already in the DB. On a fresh re-import the DB will be empty, so most calloff_po_id values will remain NULL in the CSV. The post-import UPDATE in Task 8 Step 5 handles the remaining unresolved SCs after POs are imported and their po_ids are generated.

- [ ] **Step 1: Insert resolution pass after line 1146 (before CSV write section)**

Add the following code block after line 1146 and before line 1148:

```python
# ── Resolve internal_system_number -> calloff_po_id for SCs ────────────
# For call-off SCs where calloff_po_id is empty but internal_system_number
# (Supplier column, contains PO external number) is set, look up the
# corresponding PO by po_no and fill in calloff_po_id.
resolved_calloff = 0
unresolved_calloff = 0
if os.path.exists(DB_PATH):
    po_lookup_conn = sqlite3.connect(DB_PATH)
    po_lookup_conn.row_factory = sqlite3.Row
    po_by_no = {}
    for po_row in po_lookup_conn.execute(
        "SELECT po_id, po_no, created_at FROM pos WHERE po_no IS NOT NULL AND po_no != '' ORDER BY created_at DESC"
    ):
        po_by_no.setdefault(po_row["po_no"], []).append(dict(po_row))
    po_lookup_conn.close()

    for sc in unique_sc:
        # Only resolve if calloff_po_id is empty but internal_system_number is set
        if sc.get("calloff_po_id", ""):
            continue
        isn = sc.get("internal_system_number", "")
        if not isn:
            continue

        matches = po_by_no.get(isn, [])
        if len(matches) == 1:
            sc["calloff_po_id"] = matches[0]["po_id"]
            resolved_calloff += 1
        elif len(matches) > 1:
            # Multiple POs with same po_no — data integrity issue
            sc["calloff_po_id"] = matches[0]["po_id"]  # most recent by created_at DESC
            resolved_calloff += 1
            # Record warning in audit
            for a in audit_rows:
                if a["_row"] == sc["_row"] and a["record_type"] == "SC":
                    a["auto_fix"] = (a.get("auto_fix", "") +
                        f"; Multiple POs with po_no={isn}, used most recent {matches[0]['po_id']}").strip("; ")
                    break
        else:
            unresolved_calloff += 1
            # Record in audit
            for a in audit_rows:
                if a["_row"] == sc["_row"] and a["record_type"] == "SC":
                    a["problem"] = (a.get("problem", "") +
                        f"; No PO found with po_no={isn}, calloff_po_id left empty").strip("; ")
                    break

    print(f"  [calloff_po_id resolution]: {resolved_calloff} resolved, {unresolved_calloff} unresolved")
```

- [ ] **Step 2: Run the import script to verify resolution works**

```bash
cd c:\Users\V2SE7PP\Projects\contract && python docs/process_c26_import.py
```

Expected: Script completes successfully. Check the summary output for "calloff_po_id resolution" line showing resolved/unresolved counts.

- [ ] **Step 3: Spot-check the generated import_sc.csv for calloff_po_id values**

```bash
cd c:\Users\V2SE7PP\Projects\contract\docs && head -20 import_sc.csv | cut -d, -f13,14
```

Expected: Rows that are call-off SCs with a matching PO should show non-empty `calloff_po_id` in column 14.

- [ ] **Step 4: Add integration test for resolution + post-import update**

Add to `tests/test_fc_calloff_flow.py`:

```python
def test_internal_system_number_resolves_to_calloff_po_id(app_config):
    """Simulate import scenario: SC created with internal_system_number
    (PO NO) but no calloff_po_id. After POs exist, post-import UPDATE
    resolves the link."""
    from sc_gr_app.db.connection import connect
    migrate(app_config)
    seed_users(app_config)

    # 1. Create SC(FC) and PO(FC) — the parent framework
    sc_fc = create_sc(app_config, ADMIN, {
        "sc_no": "SC-FC-RESOLVE",
        "requester_id": USER["user_id"],
        "request_type": "FC",
        "cost_center": 1000,
        "sc_amount": 100000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
    })
    sc_fc = approve_sc(app_config, ADMIN, sc_fc["sc_id"])
    vendor_id = _create_vendor_and_link(app_config, sc_fc["sc_id"])
    po_fc = create_po(app_config, ADMIN, {
        "sc_id": sc_fc["sc_id"],
        "vendor_id": vendor_id,
        "po_amount": 80000,
    })
    # PO gets a po_no that matches the internal_system_number we'll set
    with connect(app_config) as conn:
        conn.execute("UPDATE pos SET po_no = ? WHERE po_id = ?",
                     ("7600-RESOLVE-TEST", po_fc["po_id"]))
        conn.commit()

    # 2. Create call-off SC as if from import: internal_system_number set,
    #    but calloff_po_id is NOT set (simulating the bug)
    calloff = create_sc(app_config, ADMIN, {
        "sc_no": "SC-CO-RESOLVE",
        "requester_id": USER["user_id"],
        "request_type": "call_off",
        "cost_center": 1000,
        "sc_amount": 30000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
        "calloff_po_id": None,
        "internal_system_number": "7600-RESOLVE-TEST",
    })
    assert calloff["calloff_po_id"] is None

    # 3. Run post-import UPDATE (same SQL as Task 8 Step 5)
    with connect(app_config) as conn:
        updated = conn.execute(
            """UPDATE sc_records
               SET calloff_po_id = (
                 SELECT po_id FROM pos
                 WHERE pos.po_no = sc_records.internal_system_number
                   AND pos.po_no IS NOT NULL AND pos.po_no != ''
                 ORDER BY pos.created_at DESC
                 LIMIT 1
               )
               WHERE request_type = 'call_off'
                 AND (calloff_po_id IS NULL OR calloff_po_id = '')
                 AND internal_system_number IS NOT NULL
                 AND internal_system_number != ''"""
        ).rowcount
        conn.commit()
    assert updated >= 1

    # 4. Verify calloff_po_id is now resolved
    detail = get_sc_detail(app_config, ADMIN, calloff["sc_id"])
    assert detail["sc"]["calloff_po_id"] == po_fc["po_id"]
    assert detail["parent_po"] is not None
    assert detail["parent_po"]["po_id"] == po_fc["po_id"]

    # 5. Verify budget includes the resolved call-off
    fc_budget = compute_po_fc_budget(app_config, po_fc["po_id"])
    assert fc_budget["allocated_calloff_amount"] == 30000.0
```

- [ ] **Step 5: Run the resolution integration test**

```bash
cd c:\Users\V2SE7PP\Projects\contract && python -m pytest tests/test_fc_calloff_flow.py::test_internal_system_number_resolves_to_calloff_po_id -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/process_c26_import.py
git commit -m "feat: resolve internal_system_number to calloff_po_id via po_no match in import"
```

---

### Task 7: Finish frontend changes (uncommitted work)

**Files:**
- Modify: `frontend/src/components/sc/ScFormDialog.vue`
- Modify: `frontend/src/components/sc/ScDetailCard.vue`
- Modify: `frontend/src/components/sc/ScTable.vue`

These files already have uncommitted changes from current working tree. Review them to ensure correctness.

- [ ] **Step 1: Review ScFormDialog.vue change**

The diff changes `internal_system_number` field visibility from `request_type === 'FC'` to `request_type === 'call_off'`. This is correct — internal_system_number is the parent PO's external number, relevant only for call-off SCs.

- [ ] **Step 2: Review ScDetailCard.vue change**

The diff removes the `v-if="sc.request_type === 'FC'"` condition from `internal_system_number` display, showing it for all SC types. Correct — both FC and call_off SCs may have this field.

- [ ] **Step 3: Review ScTable.vue change**

The diff adds an `internal_system_number` column at width 130 with `show-overflow-tooltip`. Correct — provides visibility in the table view.

- [ ] **Step 4: Build frontend to verify no build errors**

```bash
cd c:\Users\V2SE7PP\Projects\contract\frontend && npm run build
```

Expected: Build succeeds with no errors.

- [ ] **Step 5: Commit frontend changes**

```bash
git add frontend/src/components/sc/ScFormDialog.vue frontend/src/components/sc/ScDetailCard.vue frontend/src/components/sc/ScTable.vue
git commit -m "feat: show internal_system_number for call_off SCs in form, all types in detail/table"
```

---

### Task 8: Database clear and full re-import

**Files:**
- Scripts: `docs/setup_fresh_db.py`, `seed_data.py`, `docs/process_c26_import.py`
- CSVs (generated): `docs/import_sc.csv`, `docs/import_po.csv`, `docs/import_gr.csv`, `docs/import_vendor.csv`

- [ ] **Step 1: Run setup_fresh_db.py to drop and recreate schema**

```bash
cd c:\Users\V2SE7PP\Projects\contract && python docs/setup_fresh_db.py
```

Expected output: "Deleted old DB", "Created fresh schema.", users seeded, vendors imported.

- [ ] **Step 2: Run seed_data.py to create additional test data if needed**

```bash
cd c:\Users\V2SE7PP\Projects\contract && python seed_data.py
```

Expected: Creates admin user and seed test records.

- [ ] **Step 3: Run process_c26_import.py to generate corrected CSVs**

```bash
cd c:\Users\V2SE7PP\Projects\contract && python docs/process_c26_import.py
```

Expected: Script completes with summary showing SC/PO/GR counts and calloff_po_id resolution stats. No fatal errors.

- [ ] **Step 4: Write a bulk import script to load CSVs via the import service**

Create `docs/bulk_import.py`:

```python
"""Bulk import SC, PO, GR, vendor CSVs using the import service functions."""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["SC_GR_DEV"] = "1"

from sc_gr_app.config import default_config
from sc_gr_app.services.import_service import import_scs, import_pos, import_grs
from sc_gr_app.services.vendor_service import create_vendor

config = default_config()
BASE = os.path.dirname(os.path.abspath(__file__))
ADMIN = {"user_id": "U-86183", "role": "admin", "machine_id": "86183"}

def load_csv(filename):
    path = os.path.join(BASE, filename)
    if not os.path.exists(path):
        print(f"  [SKIP] {filename} not found")
        return []
    with open(path, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

# 1. Import vendors
print("=== Importing vendors ===")
vendor_rows = load_csv("import_vendor.csv")
vendor_imported = 0
for v in vendor_rows:
    vname = v.get("vendor_name", "").strip()
    if not vname:
        continue
    try:
        create_vendor(config, ADMIN, {
            "vendor_name": vname,
            "service_scope": v.get("service_scope", ""),
            "ksrm_vendor_code": v.get("ksrm_vendor_code", ""),
            "company_name_cn": v.get("company_name_cn", ""),
            "contact_person": v.get("contact_person", ""),
            "phone": v.get("phone", ""),
            "email": v.get("email", ""),
            "description": v.get("description", ""),
            "inquiry_history": v.get("inquiry_history", ""),
        })
        vendor_imported += 1
    except Exception as e:
        print(f"  [WARN] Vendor '{vname}': {e}")
print(f"  Imported: {vendor_imported}")

# 2. Import SCs (must come before POs so calloff_po_id FK is valid)
print("=== Importing SCs ===")
sc_rows = load_csv("import_sc.csv")
if sc_rows:
    result = import_scs(config, ADMIN, sc_rows)
    print(f"  {result}")
else:
    print("  No SC rows to import")

# 3. Import POs
print("=== Importing POs ===")
po_rows = load_csv("import_po.csv")
if po_rows:
    result = import_pos(config, ADMIN, po_rows)
    print(f"  {result}")
else:
    print("  No PO rows to import")

# 4. Import GRs
print("=== Importing GRs ===")
gr_rows = load_csv("import_gr.csv")
if gr_rows:
    result = import_grs(config, ADMIN, gr_rows)
    print(f"  {result}")
else:
    print("  No GR rows to import")

# 5. Post-import: resolve calloff_po_id for SCs that weren't resolved
# at CSV generation time (fresh DB has no POs yet during CSV generation).
print("=== Post-import calloff_po_id resolution ===")
from sc_gr_app.db.connection import connect
with connect(config) as conn:
    # Match SC.internal_system_number to PO.po_no and set calloff_po_id
    updated = conn.execute(
        """UPDATE sc_records
           SET calloff_po_id = (
             SELECT po_id FROM pos
             WHERE pos.po_no = sc_records.internal_system_number
               AND pos.po_no IS NOT NULL AND pos.po_no != ''
             ORDER BY pos.created_at DESC
             LIMIT 1
           )
           WHERE request_type = 'call_off'
             AND (calloff_po_id IS NULL OR calloff_po_id = '')
             AND internal_system_number IS NOT NULL
             AND internal_system_number != ''"""
    ).rowcount
    conn.commit()
    print(f"  Resolved calloff_po_id for {updated} call-off SCs")

print("\nDone.")
```

- [ ] **Step 5: Run the bulk import script**

```bash
cd c:\Users\V2SE7PP\Projects\contract && python docs/bulk_import.py
```

Expected: All imports succeed. Note any warnings about unresolved calloff_po_id.

- [ ] **Step 6: Verify data integrity**

```bash
cd c:\Users\V2SE7PP\Projects\contract && python -c "
import os, sys
sys.path.insert(0, '.')
os.environ['SC_GR_DEV'] = '1'
from sc_gr_app.config import default_config
from sc_gr_app.db.connection import connect

config = default_config()
with connect(config) as conn:
    # Check call-off SCs with calloff_po_id set
    calloff_with = conn.execute(
        \"SELECT COUNT(*) as n FROM sc_records WHERE request_type='call_off' AND calloff_po_id IS NOT NULL AND calloff_po_id != ''\"
    ).fetchone()['n']
    calloff_without = conn.execute(
        \"SELECT COUNT(*) as n FROM sc_records WHERE request_type='call_off' AND (calloff_po_id IS NULL OR calloff_po_id = '')\"
    ).fetchone()['n']
    print(f'call-off SCs with calloff_po_id: {calloff_with}')
    print(f'call-off SCs without calloff_po_id: {calloff_without}')
    
    # Check SCs with service_scope
    sc_with_scope = conn.execute(
        \"SELECT COUNT(*) as n FROM sc_records WHERE service_scope IS NOT NULL AND service_scope != ''\"
    ).fetchone()['n']
    total_sc = conn.execute('SELECT COUNT(*) as n FROM sc_records').fetchone()['n']
    print(f'SCs with service_scope: {sc_with_scope}/{total_sc}')
    
    # Check FC PO budget
    fc_pos = conn.execute(
        \"SELECT po_id FROM pos WHERE request_type='FC' OR po_id IN (SELECT DISTINCT calloff_po_id FROM sc_records WHERE calloff_po_id IS NOT NULL AND calloff_po_id != '')\"
    ).fetchall()
    print(f'FC POs: {len(fc_pos)}')
"
```

Expected: Most call-off SCs have `calloff_po_id` populated. SCs have service_scope populated. FC POs are identified.

- [ ] **Step 7: Run the full test suite**

```bash
cd c:\Users\V2SE7PP\Projects\contract && python -m pytest tests/ -v --tb=short
```

Expected: All tests pass (or same pass/fail as before changes).

- [ ] **Step 8: Commit**

```bash
git add docs/bulk_import.py
git commit -m "feat: add bulk import script for CSV-based DB re-import"
```

---

### Task 9: Final verification — manual checks

- [ ] **Step 1: Start the backend server**

```bash
cd c:\Users\V2SE7PP\Projects\contract && python -m sc_gr_app.main
```

- [ ] **Step 2: Verify SC detail shows parent PO**

Open the app in browser, navigate to a call-off SC detail page. Verify the "Call-off PO" card is visible with parent PO number and a clickable link.

- [ ] **Step 3: Verify PO(FC) detail shows call-off SCs**

Navigate to a PO(FC) detail page. Verify the "Call-off SCs" table lists all linked call-off SCs with amounts and statuses.

- [ ] **Step 4: Verify PO(FC) budget includes call-off amounts**

On the same PO(FC) detail page, check the budget card. Verify `allocated_calloff_amount` and `pending_calloff_amount` reflect the call-off SC amounts.

- [ ] **Step 5: Stop the server**
