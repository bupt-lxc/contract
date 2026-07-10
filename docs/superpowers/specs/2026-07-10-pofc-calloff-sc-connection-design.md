# PO(FC) and Call-off SC Connection Fix

**Date:** 2026-07-10
**Status:** approved

## Problem

PO(FC) and call-off SC are disconnected in the system:

1. **SC detail cannot navigate to parent PO(FC):** Imported call-off SCs have
   `internal_system_number` (populated from the Supplier column of the source
   Excel, which in the C26.4 dataset contains the parent PO's external number)
   but `calloff_po_id` is NULL. The `parent_po` card in SC detail depends on
   `calloff_po_id`.
2. **PO(FC) detail shows no call-off SC list:** Backend queries
   `WHERE calloff_po_id = ?`, missing all imported SCs.
3. **PO(FC) budget calculation omits call-off SC amounts:**
   `compute_po_fc_budget` directly queries `sc_records WHERE calloff_po_id = ?`;
   `compute_sc_fc_budget` traces through `pos` joined on `sc_records.calloff_po_id`.
   Both require `calloff_po_id` to be populated, so imported SCs are invisible.

## Root Cause

Two connection paths exist but never meet:

- **Internal path:** `calloff_po_id` — set when SC is created via UI; used by all
  backend queries and budget calculations.
- **External path:** `internal_system_number` — populated during import from the
  Supplier column of the source Excel (which in practice contains PO external
  numbers); has no mapping to internal `po_id`.

The import pipeline also drops fields during DB insert: `service_scope`,
`calloff_po_id`, and `asset_nums` are present in the generated CSV but the
`INSERT INTO sc_records` statement in `import_service.py` does not include them.

Additionally, `update_sc` accepts `service_scope` in its validation allow-list
but does not include it in the UPDATE SET columns — edits to `service_scope`
are silently ignored.

## Solution

**Strategy:** Resolve `internal_system_number` → `po_id` at import time, so
`calloff_po_id` is always populated. Fix the import INSERT and update to include
all columns. Fix the downloadable SC template to match.

### Part 1: import_service.py — fix INSERT and column mapping

**File:** [sc_gr_app/services/import_service.py](sc_gr_app/services/import_service.py#L171)

Add `service_scope`, `calloff_po_id`, `asset_nums` to the INSERT columns and values:

```python
conn.execute(
    """INSERT INTO sc_records (
      sc_id, sc_no, requester_id, request_type, cost_center,
      sc_amount, service_period_start, service_period_end,
      status, description, currency, internal_system_number,
      service_scope, calloff_po_id, asset_nums,
      created_by, created_at, updated_at, asset
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'N')""",
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
        row.get("service_scope"),          -- new
        row.get("calloff_po_id"),          -- new
        row.get("asset_nums"),             -- new
        current_user["user_id"],
        timestamp,
        timestamp,
    ),
)
```

Note: `calloff_po_id` has a FK to `pos(po_id)` with NULL allowed. The import order
must ensure referenced POs exist before call-off SCs are imported. If a referenced
PO is not yet imported, leave `calloff_po_id` NULL and update it in a post-import pass.

Also add `service_scope`, `calloff_po_id`, `asset_nums`, and `asset` to the
`_SC_COLUMN_ALIASES` dict (around line 335) for backend-side header matching
consistency. The frontend uses XLSX directly and is not affected, but the mapping
should be complete for any future backend-side parsing.

### Part 2: process_c26_import.py — resolve internal_system_number → calloff_po_id

**File:** [docs/process_c26_import.py](docs/process_c26_import.py)

**Insertion point:** After the SC date inheritance block (after line 1069, before
the CSV write section at line 1148). The resolution pass operates on `unique_sc`
(the deduplicated list).

**Logic:** For each SC row where `calloff_po_id` is empty (falsy) but
`internal_system_number` is set:

1. Query DB: `SELECT po_id FROM pos WHERE po_no = ?` with `internal_system_number`
2. If one match found → set `calloff_po_id` to matched `po_id`
3. If zero matches → record in audit: "No PO found with po_no=X, calloff_po_id left empty"
4. If multiple matches → this indicates a data integrity problem (duplicate `po_no`
   values). Take the most recent by `created_at` as a fallback, but log a warning
   in audit.

Rows that already have a `calloff_po_id` (e.g., from `extract_7600_po` in the main
loop) are skipped — the existing value takes precedence.

**DB connection:** The script opens a DB connection at line 28 and closes it at
line 38. Move `conn.close()` to after the resolution pass and CSV writing, so the
connection is available for the resolution query. Alternatively, open a second
connection specifically for the resolution pass.

### Part 3: import_service.py — fix import_pos INSERT to include request_type

**File:** [sc_gr_app/services/import_service.py](sc_gr_app/services/import_service.py#L284)

The `import_pos` INSERT has 18 columns but does not include `request_type`.
Currently this is masked because `_validate_po_rows` requires `sc_no` (blocking
independent PO import), but if the validator is ever relaxed, independent FC POs
would silently lose their `request_type`, breaking `is_fc_po` checks everywhere.

Add `request_type` to the INSERT columns and `row.get("request_type")` to the
values tuple.

### Part 5: sc_service.py — fix update_sc to write service_scope

**File:** [sc_gr_app/services/sc_service.py](sc_gr_app/services/sc_service.py#L866)

Add `service_scope = ?` to the UPDATE SET columns and include
`merged.get("service_scope")` in the parameter tuple. `service_scope` is already
in `OPTIONAL_UPDATE_FIELDS` (line 46) but is missing from the actual UPDATE
statement.

### Part 6: bridge.py — fix downloadable SC template

**File:** [sc_gr_app/api/bridge.py](sc_gr_app/api/bridge.py#L1885)

Add `service_scope`, `calloff_po_id`, `asset_nums`, and `asset` to the
`download_sc_template` headers, hints, and sample arrays. Users who download the
template and manually import SCs currently cannot populate these fields.

### Part 7: Database clear and re-import

Procedure:

1. `python docs/setup_fresh_db.py` — drops all tables and recreates schema
2. `python seed_data.py` — recreates users, vendors
3. `python docs/process_c26_import.py` — generates corrected CSVs with resolved
   `calloff_po_id` and `service_scope`
4. Import CSVs into the system:
   - Import vendors via `import_vendor.csv` (frontend Import page or script)
   - Import SCs via `import_sc.csv`
   - Import POs via `import_po.csv`
   - Import GRs via `import_gr.csv`
5. Verify: check SC detail shows parent PO, PO(FC) detail lists call-off SCs,
   budget amounts include call-off totals

### Part 8: Frontend (already in progress, finish current work)

These three files have uncommitted changes that should be completed:

- **ScFormDialog.vue:** `internal_system_number` input shown for `call_off` type
- **ScDetailCard.vue:** `internal_system_number` displayed for all SC types
- **ScTable.vue:** `internal_system_number` column added

`ScDetailView.vue` parent_po card is already committed (6d227f4). No additional
frontend changes are needed — the data fix at the import layer makes the existing
UI work correctly.

## Data Flow (after fix)

```
Excel import
  → process_c26_import.py
    → resolves internal_system_number → po_id via po_no match
    → sets calloff_po_id on SC rows
    → writes corrected CSV (import_sc.csv with calloff_po_id + service_scope)
  → import_service.py (import_scs)
    → INSERT includes calloff_po_id, service_scope, asset_nums
    → SC stored with correct calloff_po_id

At runtime:
  SC detail → parent_po card visible (via calloff_po_id)
  PO(FC) detail → call-off SCs listed (via calloff_po_id)
  Budget calculation → includes all call-off SCs (via calloff_po_id)
```

## Verification

- [ ] `import_scs` INSERT includes service_scope, calloff_po_id, asset_nums
- [ ] `import_pos` INSERT includes request_type
- [ ] `_SC_COLUMN_ALIASES` includes service_scope, calloff_po_id, asset_nums, asset
- [ ] `update_sc` UPDATE includes service_scope
- [ ] `download_sc_template` includes service_scope, calloff_po_id, asset_nums, asset
- [ ] `process_c26_import.py` resolves internal_system_number → calloff_po_id
- [ ] Imported SCs in UI show parent_po card with valid link
- [ ] PO(FC) detail lists all call-off SCs including imported ones
- [ ] PO(FC) budget shows allocated_calloff_amount matching call-off SC totals
- [ ] Database clear + full re-import succeeds without errors
