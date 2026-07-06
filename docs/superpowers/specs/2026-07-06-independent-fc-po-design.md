# Independent FC PO Design

Date: 2026-07-06

## Summary

Allow creating PO(FC) directly without a parent SC(FC). Currently every PO must belong to an SC, and PO type (FC vs regular) is derived from the parent SC. This change allows:

- **Independent FC PO**: `sc_id IS NULL`, `request_type = 'FC'` — no upstream budget cap, all fields filled manually, draft → active → finished lifecycle
- **Regular PO**: `sc_id IS NOT NULL`, `request_type IS NULL` — existing behavior unchanged, type derived from parent SC

The `sc_id` field on `pos` becomes nullable, and a new `request_type` column is added to `pos`.

---

## Data Model

### Migration v33

Rebuild `pos` table:

```sql
CREATE TABLE pos_new (
  po_id TEXT PRIMARY KEY,
  sc_id TEXT REFERENCES sc_records(sc_id),           -- NULL allowed (independent FC PO only)
  vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
  po_no TEXT,
  requester_id TEXT,
  po_amount REAL NOT NULL CHECK (po_amount > 0),
  status TEXT NOT NULL CHECK (status IN ('draft','active','finished')),
  request_type TEXT CHECK (request_type IN ('FC')),  -- NEW: only set for independent FC PO
  contract_from TEXT,
  contract_to TEXT,
  contract_no TEXT,
  payment_frequency TEXT,
  contract_pos TEXT,
  contract_type TEXT,
  cost_center TEXT,
  purchaser TEXT,
  active_date TEXT,
  finished_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

Rebuild `gr_requests` to fix FK references after `pos` table rebuild (same pattern as previous migrations v9/v12/v30).

### Semantics

| sc_id | request_type | Meaning |
|---|---|---|
| NOT NULL | NULL | Regular PO, type derived from parent SC (existing behavior) |
| NULL | `'FC'` | Independent FC PO (new) |
| NOT NULL | `'FC'` | Invalid (rejected — when SC exists, type is derived from SC) |
| NULL | NULL | Invalid (rejected — must specify type when no SC) |

### Effective type

`COALESCE(pos.request_type, sc_records.request_type)` is the canonical PO type for queries.

---

## Backend Changes

### po_service.py

**REQUIRED_FIELDS** changes from `("sc_id", "vendor_id", "po_amount")` to `("vendor_id", "po_amount")`.

**create_po** — branching logic:

```
if sc_id is None:
    - request_type must be 'FC'
    - requester_id = current_user.user_id (or data["requester_id"] if provided)
    - Skip: SC existence/status check, SC owner check, vendor-SC link check, SC budget check
    - Initial status = data.get("status", "draft")
    - Lock key: f"po:{po_id}" (instead of f"sc:{sc_id}")
    - cost_center = data.get("cost_center") (no SC inheritance)
else:
    - Existing logic unchanged
    - request_type must NOT be set in data (type comes from SC)
```

**submit_po** — when sc_id is null:

- Skip SC status/draft check
- Skip SC budget check
- Still validate: PO is in draft status

**update_po** — when sc_id is null:

- Skip SC status/owner checks
- Skip vendor-SC link check
- Skip `calloff_po_id` downstream check (no SC tying the budget)
- Still validate: po_amount ≥ sum of call-off SC amounts

**finish_po** — when sc_id is null:

- Skip SC finished check
- Still check: all call-off SCs in final state

**recall_po** — when sc_id is null:

- Check PO owner directly (not SC requester)
- Still check: no non-draft call-off SCs

**delete_po** — when sc_id is null:

- Check PO owner directly
- Still check: no call-off SCs exist

**Lock strategy**: when `sc_id` is null, use `f"po:{po_id}"` as the lease key.

### budget_service.py

- `compute_po_budget(po_id)`: when `sc_id IS NULL`, skip SC-level aggregation. Still compute downstream (call-off SCs, GRs).
- `compute_po_fc_budget(po_id)`: applies to independent FC PO as-is — computes from `po_amount` down through call-off SCs.

### query_service.py

**search_pos**:

- `sc_records` JOIN → LEFT JOIN (sc_id may be null)
- `sc_request_type` = `COALESCE(pos.request_type, sc.request_type)`
- `open_po_amount`: when `sc_id IS NULL AND pos.request_type = 'FC'`, use call-off allocation formula instead of GR formula (same as existing FC PO logic)
- `is_fc_po` filter: match when `pos.request_type = 'FC'` OR parent SC is FC

**search_scs / workbench_data**: no changes needed (independent FC PO has no SC).

### gr_service.py

**create_gr**: extend the FC rejection check:

```
if pos.request_type = 'FC' OR parent_sc.request_type = 'FC':
    reject "FC PO cannot create GRs"
```

### export_service.py

- PO export columns: add `request_type`, keep `sc_id` (outputs empty when null)
- SC cascade export: no impact (independent FC PO has no parent SC)

### import_service.py

- PO import template: add `request_type` column (optional, only "FC")
- Validations:
  - `sc_id` + `request_type = 'FC'` both set → error
  - `sc_id` empty + `request_type != 'FC'` → error
  - Independent FC PO: skip SC-related validations

### notification_service.py

- `thresholds.py`: for independent FC PO (`sc_id IS NULL`, `request_type = 'FC'`), compute `consumed` from call-off SC amounts (same as existing FC PO path)
- `monthly.py`: same fix — use call-off allocation for FC PO budget math

### api/bridge.py

- `download_po_template`: add `request_type` to header row
- `search_pos` / `get_po_detail`: `is_fc_po` filter covers both `pos.request_type = 'FC'` and SC-derived FC
- `get_po_detail`: change `sc_records` JOIN to LEFT JOIN so independent FC PO returns detail without SC info
- `add_attachments`: when `parent_sc_id` is null (independent FC PO), skip the SC attachment directory; store PO attachments directly under the PO directory

### notification_service.py — additional changes

In `create_po`, the "create" notification currently reads `sc["requester_id"]`. For independent FC PO, `sc` is None. Use the PO's own requester_id:

```
notification_service.queue_status_change(
    conn, "po", po_id, "create",
    {"requester_id": created["requester_id"]},
    {"user_id": current_user["user_id"], "machine_id": current_user["machine_id"]}
)
```

Other status change calls (submit/finish/recall) already use `if sc else {}` pattern, which handles null sc_id gracefully.

---

## Frontend Changes

### PoListView — Create PO dropdown

"New PO" button becomes a split-button/dropdown:

- **New Regular PO** → SC selection dialog → PoFormDialog (sc_id required)
- **New FC PO** → PoFormDialog directly (sc_id hidden, request_type fixed to FC)

### PoFormDialog

| Field | Regular PO | Independent FC PO |
|---|---|---|
| SC selection | Required (pre-filled from dialog) | Hidden |
| request_type | Hidden (from SC) | Hidden (fixed "FC") |
| vendor | Filtered by SC's vendors | All active vendors |
| requester | Inherited from SC | Default: current user, editable |
| cost_center | Inherited from SC, editable | Manual input |
| Other fields | Unchanged | Unchanged |
| Save / Save Draft | Create/submit via createPo | Create/submit via createPo (without sc_id) |

### PoTable

- `sc_id` column: show "—" when null
- Type column: show "FC" tag from `COALESCE(pos.request_type, sc.request_type)`

### PoDetailView

- When `sc_id` is null: hide "SC info" section and "Open SC Detail" link
- FC PO budget and call-off SC list: existing FC PO rendering applies (keyed on effective `request_type`)
- GR section: hidden for FC POs (already conditional on FC type)

### ScDetailView

No changes needed (independent FC PO has no SC parent).

---

## Lifecycle & Constraints

### Independent FC PO lifecycle

```
draft → (submit) → active → (finish) → finished
                  ↓
              (recall) → draft
```

### Creation rules

| Entity | Parent constraint |
|---|---|
| Independent FC PO | None (no SC required) |
| Regular PO | SC draft or approved (existing) |
| Call-off SC | PO(FC) active (existing) |

### Finish cascade

Independent FC PO finish requires all child call-off SCs in final state (same as SC-bound FC PO).

### Budget chain (independent FC PO)

```
PO(FC) po_amount (no upstream cap)
  └─ sum(call-off SC amounts) ≤ PO(FC) amount
       └─ sum(regular PO amounts) ≤ SC amount (existing)
            └─ sum(GR amounts) ≤ PO amount (existing)
```

### Vendor constraints

Independent FC PO has no SC vendor restrictions — vendor is freely chosen. Call-off SCs under the FC PO follow their own vendor linking rules.

---

## Edge Cases

1. **Existing data**: all existing POs have `sc_id` set. Migration makes `sc_id` nullable but doesn't change existing data. `request_type` is null for all existing POs (type derived from SC as before).

2. **sc_id immutability**: `sc_id` cannot be changed after creation. The `update_po` allowed fields list does not include `sc_id`.

3. **Lock contention**: independent FC PO uses `po:{po_id}` lock key, avoiding false contention with SC locks.

4. **PO(FC) transferred to another requester**: not supported in current system. If added later, independent FC PO owner check must be updated alongside SC-bound PO owner check.

5. **Vendor-SC consistency**: call-off SCs under independent FC PO can have different vendors from the PO(FC). This is consistent with existing FC behavior (no vendor matching enforced between PO(FC) and call-off SCs).

6. **Two-level nesting**: independent FC PO still respects the two-level limit — call-off SCs cannot be FC type, preventing deeper nesting.
