# Independent FC PO Design

Date: 2026-07-06 (updated after review)

## Summary

Allow creating PO(FC) directly without a parent SC(FC). Currently every PO must belong to an SC, and PO type (FC vs regular) is derived from the parent SC. This change allows:

- **Independent FC PO**: `sc_id IS NULL`, `request_type = 'FC'` — no upstream budget cap, all fields filled manually, draft → active → finished lifecycle
- **Regular PO**: `sc_id IS NOT NULL`, `request_type IS NULL` — existing behavior unchanged, type derived from parent SC

The `sc_id` field on `pos` becomes nullable, and a new `request_type` column is added to `pos`.

---

## Data Model

### Migration v33

Rebuild `pos` table (make `sc_id` nullable, add `request_type`):

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

Rebuild `gr_requests` to fix FK references after `pos` table rebuild (same pattern as v9/v12/v30).

### Semantics

| sc_id | request_type | Meaning |
|---|---|---|
| NOT NULL | NULL | Regular PO, type derived from parent SC (existing behavior) |
| NULL | `'FC'` | Independent FC PO (new) |
| NOT NULL | `'FC'` | Invalid (rejected at creation) |
| NULL | NULL | Invalid (rejected at creation) |

### Effective type

`COALESCE(pos.request_type, sc_records.request_type)` is the canonical PO type for any query joining both tables.

---

## Backend Changes

### sc_service.py

**`_validate_calloff_po`** (line 68) — **Critical**: This is the gate for creating call-off SCs under a PO(FC). The query at line 81 uses INNER JOIN:

```sql
select po.po_id, po.po_amount, po.status, sc.request_type as parent_sc_type
from pos po
join sc_records sc on sc.sc_id = po.sc_id
where po.po_id = ?
```

For independent FC PO (`sc_id IS NULL`), the JOIN returns nothing → `NotFound("PO not found: {calloff_po_id}")`. **Cannot create any call-off SC under independent FC PO.**

Fix:
```sql
select po.po_id, po.po_amount, po.status, po.request_type as po_request_type,
       sc.request_type as parent_sc_type
from pos po
left join sc_records sc on sc.sc_id = po.sc_id
where po.po_id = ?
```

Then update the FC validation (line 87-88):
```python
# OLD: if po_row["parent_sc_type"] != "FC":
# NEW: check both PO-level and SC-level type
is_fc_po = (po_row["po_request_type"] == "FC" or po_row["parent_sc_type"] == "FC")
if not is_fc_po:
    raise ValidationError("Call-off PO must be an FC-type PO (either independent or under SC(FC))")
```

Status check (line 89-90): `po_row["status"] != "active"` — still works (reads from `pos` directly).

Budget check (line 103-104): `po_row["po_amount"]` — still works (reads from `pos` directly).

**Callers**: `create_sc` (line 481), `create_sc_draft` (line ~575), `submit_sc` (line ~680). All share this fix.

**`update_sc` call-off budget check** (lines 824-836): Already safe — queries `pos` directly without `sc_records` JOIN.

**`get_sc_detail` — parent PO info for call-off SCs** (lines 1247-1252): Uses INNER JOIN `join sc_records sc_parent on sc_parent.sc_id = po.sc_id` to fetch parent PO info. For call-off SC under independent FC PO, this returns null → parent PO info not shown. Fix: LEFT JOIN.

---

### po_service.py

**REQUIRED_FIELDS** changes from `("sc_id", "vendor_id", "po_amount")` to `("vendor_id", "po_amount")`. `sc_id` is validated conditionally inside the function.

**create_po** — branching logic:

```
if sc_id is None:
    - request_type must be 'FC'
    - requester_id = current_user.user_id (or data["requester_id"] if provided)
    - Skip: SC existence/status check, SC owner check, vendor-SC link check, SC budget check
    - Initial status = data.get("status", "draft")
    - Lock key: f"po:{po_id}" (instead of f"sc:{sc_id}")
    - cost_center = data.get("cost_center") (no SC inheritance)
    - Notification: pass created["requester_id"] directly (sc is None, cannot use sc["requester_id"])
else:
    - Existing logic unchanged
    - request_type must NOT be set in data (type comes from SC)
```

**submit_po** — when sc_id is null:

- Lock key: `f"po:{sc_id_or_po_id}"` — find sc_id from the PO first; if null, use `f"po:{po_id}"`
- Skip SC status/draft check
- Skip SC budget check
- Still validate: PO is in draft status

**update_po** — when sc_id is null:

- Lock key: same branching as submit_po
- Skip SC status/owner checks
- Skip vendor-SC link check
- Skip `calloff_po_id` downstream check (no SC tying the budget)
- Still validate: po_amount >= sum of call-off SC amounts

**finish_po** — when sc_id is null:

- Lock key: same branching
- Skip SC finished check
- Still check: all call-off SCs in final state

**recall_po** — when sc_id is null:

- Lock key: same branching
- Check PO owner directly (not SC requester): `po["requester_id"] != current_user["user_id"]`
- Skip SC status and requester checks
- Still check: no non-draft call-off SCs

**delete_po** — when sc_id is null:

- Lock key: same branching
- Check PO owner directly: `po["requester_id"] != current_user["user_id"]`
- Skip SC owner check
- Still check: no call-off SCs exist

**Lock strategy summary**: when `sc_id` is present, use `f"sc:{sc_id}"` as before. When `sc_id` is null, use `f"po:{po_id}"`.

---

### budget_service.py

**`compute_po_budget(po_id)`** (lines 268-321): No changes needed. This function only queries `pos` and `gr_requests` by `po_id` — zero `sc_records` lookups. Independent FC PO works as-is because it never reads `sc_id` from the PO row.

**`compute_po_fc_budget(po_id)`** (lines 91-171): Must be fixed. Currently at lines 101-107 it fetches the parent SC via `sc_records where sc_id = ?` and raises `NotFound` when null. Fix:

```python
po = conn.execute(
    "select po_amount, sc_id, request_type from pos where po_id = ?",
    (po_id,),
).fetchone()
if po is None:
    raise NotFound(f"PO not found: {po_id}")

# For independent FC PO, skip SC lookup and validation
if po["sc_id"] is not None:
    sc = conn.execute(
        "select request_type from sc_records where sc_id = ?",
        (po["sc_id"],),
    ).fetchone()
    if sc is None:
        raise NotFound(f"PO references non-existent SC: {po['sc_id']}")
    if sc["request_type"] != "FC":
        raise ValidationError("PO is not under an FC-type SC")
elif po["request_type"] != "FC":
    raise ValidationError("PO is not an FC-type PO")
```

The downstream queries (calloff totals at lines 129-139, GR totals at lines 141-157) trace through `sc_records where calloff_po_id = ?` and do NOT depend on the parent SC. They work correctly for independent FC POs as-is.

**`compute_po_budget`** (non-FC version): No SC aggregation exists in this function. The spec's original statement about "skip SC-level aggregation" is moot — the function is already safe. No code change needed.

---

### query_service.py

**`search_pos`** — multiple changes needed:

1. **INNER JOIN → LEFT JOIN** (line 407): `join sc_records sc on sc.sc_id = po.sc_id` becomes `left join sc_records sc on sc.sc_id = po.sc_id`. Without this, independent FC POs are invisible in search results.

2. **`sc_request_type` in SELECT** (line ~393): Add `COALESCE(pos.request_type, sc.request_type) as sc_request_type`. This ensures independent FC POs properly report their FC type.

3. **`open_po_amount` CASE** (lines 398-402): The CASE checks `sc.request_type = 'FC'`. For independent FC PO, `sc.request_type` is NULL. Fix:
   ```sql
   CASE WHEN pos.request_type = 'FC' OR sc.request_type = 'FC'
     THEN po.po_amount - COALESCE(calloff_totals.allocated, 0)
     ELSE po.po_amount - COALESCE(gr_totals.pending_total, 0)
          - COALESCE(gr_totals.con_value_total, 0)
   END as open_po_amount
   ```

4. **`is_fc_po` filter** (lines 381-386): Change from `sc.request_type = 'FC'` to `(pos.request_type = 'FC' OR sc.request_type = 'FC')`.

5. **`_sc_visibility_clauses`** (lines 119-138, invoked at line 379): This function generates `sc.status != 'draft'` and `sc.requester_id = ?` clauses. After LEFT JOIN, sc columns are all NULL for independent FC POs. For non-admin users, `sc.status != 'draft'` evaluates to NULL (not TRUE), silently excluding independent FC POs.

   **Fix**: Add fallback for independent FC POs — when `po.sc_id IS NULL`, visibility is based on PO's own fields:
   - For admins: `_sc_visibility_clauses` already returns empty clauses — admins see all POs. No change needed.
   - For requesters (non-admin): add `OR (po.sc_id IS NULL AND po.requester_id = ?)` alongside existing SC visibility clauses.
   - For unauthenticated: independent FC POs are hidden (consistent with SC-based POs).

   **Visibility rule**: Independent FC PO is visible to its requester and all admins (same as regular PO).

6. **`sc_id` filter** (line 453): Currently `"sc_id": "po.sc_id"` with `= ?` binding. Independent FC POs have null sc_id and cannot be found. Add a new filter `is_independent`:
   - `"1"` → `po.sc_id IS NULL` (find all independent FC POs)
   - `"0"` → `po.sc_id IS NOT NULL` (existing behavior)

7. **Sorting on `sc.sc_no`** (line 488): NULLs sort first/last in SQLite — acceptable cosmetic behavior. No fix needed.

**`workbench_data`** (lines 641-763): Must be changed — spec was wrong to say "no changes needed."

- **Line 718**: `JOIN sc_records sc ON sc.sc_id = po.sc_id` → LEFT JOIN. Without this, independent FC POs are excluded from workbench.
- **Lines 712-715**: Same `open_po_amount` CASE fix as `search_pos` (check `pos.request_type = 'FC' OR sc.request_type = 'FC'`).
- **COUNT vs ROWS mismatch**: The COUNT at line 704 uses no JOIN (`SELECT COUNT(*) FROM pos po`), which would include independent FC POs. But the detail ROWS at line 707 use the INNER JOIN. After the LEFT JOIN fix, COUNT and ROWS are consistent again.

**`search_grs`**: No changes needed. GRs under call-off SCs always have a valid `sc_id` (the call-off SC), never trace through an independent FC PO.

---

### gr_service.py

Defense-in-depth: add FC guards to ALL operations (not just `create_gr`).

**`create_gr`** — critical fix needed:

The current INNER JOIN at line 185 (`from pos join sc_records sc on sc.sc_id = pos.sc_id`) causes `NotFound("PO not found")` for independent FC POs before reaching the FC check at line 193.

**Fix — restructure the lookup in two steps:**

```python
# Step 1: Look up PO alone (independent of SC)
lookup = lookup_conn.execute(
    "select po.sc_id, po.request_type, po.requester_id "
    "from pos po where po.po_id = ?",
    (po_id,),
).fetchone()
if lookup is None:
    raise NotFound(f"PO not found: {po_id}")

# Step 2: Reject FC POs immediately (before any SC join)
is_fc = (lookup["request_type"] == "FC")
if not is_fc:
    # Only join SC for non-FC POs to get requester info
    sc_info = lookup_conn.execute(
        "select sc.requester_id, sc.request_type "
        "from sc_records sc where sc.sc_id = ?",
        (lookup["sc_id"],),
    ).fetchone()
    if sc_info and sc_info["request_type"] == "FC":
        is_fc = True

if is_fc:
    raise ConflictError("Cannot create GR under an FC PO. Create a call-off SC instead.")
```

**All other GR operations** — add explicit FC gate at entry:

Every operation (`submit_gr`, `confirm_gr`, `approve_gr`, `deny_gr`, `finish_gr`, `recall_gr`, `update_gr`, `delete_gr`) uses `_get_gr_sc_id` or `_get_po_sc` to find the parent SC. For GRs under call-off SCs (which trace back to an independent FC PO), the call-off SC's `sc_id` is non-null, so sc_id-based queries work normally.

However, for defense-in-depth, add a check after the initial GR/PO lookup:

```python
# After fetching PO info, before any mutation:
po_request_type = po.get("request_type") or conn.execute(
    "select request_type from sc_records where sc_id = ?",
    (po["sc_id"],)
).fetchone()["request_type"]
if po_request_type == "FC":
    raise ConflictError("GRs cannot be created or modified under FC POs")
```

This ensures that even if a GR somehow exists under an FC PO (DB corruption, migration bug), the error message is clear rather than producing cryptic `sc:None` lock errors.

**Lock keys**: All 9 GR operations use `f"sc:{sc_id}"`. For GRs under call-off SCs (the only valid path), `sc_id` is the call-off SC's ID — always non-null. The lock key is valid. The FC gate at creation ensures GRs never exist directly under an independent FC PO, so `sc_id` is never null. No lock fix needed beyond the FC gate.

---

### export_service.py

**`_build_po_cascade`** — FC type detection at line 110 is wrong for independent FC POs:

Lines 94-98 fetch `request_type` only from `sc_records`:
```python
sc = conn.execute(
    "SELECT sc_no, request_type FROM sc_records WHERE sc_id = ?",
    (po["sc_id"],),
).fetchone()
sc_request_type = sc["request_type"] if sc else ""
```

For independent FC PO, `sc` is None and `sc_request_type = ""`. Line 110 checks `if sc_request_type == "FC"` — this evaluates to false, falling to the GR branch (line 123) instead of the call-off SC branch (line 111).

**Fix**: Use effective type:
```python
effective_type = po.get("request_type") or (sc["request_type"] if sc else "")
# Then use effective_type == "FC" at line 110
```

Also add `pos.request_type` to the row data returned by the PO query that feeds `_build_po_cascade`.

**`_build_gr_rows`**, **`_build_sc_cascade`**: No changes needed. SC cascade naturally excludes independent FC POs (they have no SC parent).

---

### import_service.py

**`_validate_po_rows`** (line 188):

1. **Required fields** (line 194): Change from `["sc_id", "po_no", "po_amount", "status"]` to `["po_no", "po_amount", "status"]`. `sc_id` is conditionally required:
   - When `row.get("request_type") == "FC"` and `sc_id` is empty → allowed (independent FC PO)
   - When `row.get("request_type") != "FC"` and `sc_id` is empty → error

2. **Semantic validation**: Add checks for the four-cell combinations:
   ```
   if row.get("sc_id") and row.get("request_type") == "FC":
       → error: "When sc_id is provided, request_type is derived from SC. Do not set request_type."
   if not row.get("sc_id") and row.get("request_type") != "FC":
       → error: "When sc_id is empty, request_type must be 'FC'."
   ```

3. **SC existence check** (lines 200-205): Already conditional on `if row.get("sc_id")` — correct as-is.

**`import_pos`** (line 248):

1. **INSERT statement** (lines 249-254): Add `request_type` to column list and values.
2. **`row["sc_id"]` → `row.get("sc_id")`** at lines 257 and 281. Dict access (`row["sc_id"]`) crashes with `KeyError` when CSV column is empty. Use `.get()`.

**`preview_po_import`** (lines 347-377): Apply the same changes:
1. Required fields list — same conditional sc_id logic
2. Semantic validation — same four-cell checks
3. SC existence check — already conditional, fine

**`_validate_sc_rows` — calloff_po_id validation** (lines 120-124): When SC import validates that `calloff_po_id` references an FC PO, it uses:
```sql
select 1 from pos po join sc_records sc on sc.sc_id = po.sc_id
where po.po_id = ? and sc.request_type = 'FC'
```
This INNER JOIN excludes independent FC POs. Fix:
```sql
select 1 from pos po left join sc_records sc on sc.sc_id = po.sc_id
where po.po_id = ? and (po.request_type = 'FC' or sc.request_type = 'FC')
```

**`PO_IMPORT_ALLOWED_STATUSES`** (line 185): Independent FC PO can be draft. Add `"draft"` to the set (or conditionally allow draft for FC POs only). For regular POs, draft import is still blocked (budget lock concerns).

**Download template** (`download_po_template` in bridge.py):
- Add `request_type` to headers (line 1904), hints (line 1908), and sample (line 1914)
- Update `sc_id` hint from "Required (must exist)" to "Required for regular PO; leave empty for independent FC PO (set request_type=FC)"
- Update info text (line 1941): "Required fields: PO NO, PO Amount, Status. SC ID is required for regular POs."
- Add a second sample row demonstrating independent FC PO (sc_id empty, request_type=FC)

---

### notification_service.py

**`thresholds.py`** — `check_all_active_pos` (line 19):

The query at line 28 uses `JOIN sc_records sc ON sc.sc_id = po.sc_id` (INNER JOIN). Independent FC POs are completely excluded from threshold checks — date and amount thresholds never fire for them.

Fix:
1. Change to `LEFT JOIN sc_records sc ON sc.sc_id = po.sc_id`
2. Update the `remaining` calculation (lines 21-26) to handle null `sc.request_type`:
   ```sql
   CASE WHEN pos.request_type = 'FC' OR sc.request_type = 'FC'
     THEN calloff_totals.allocated
     ELSE gr_totals.con_value_total
   END
   ```
3. `sc.requester_id` will be NULL for independent FC POs. `requester_id = po["requester_id"]` (line 70) — but `po["requester_id"]` comes from `po.*` in the SELECT (line 20), where `sc.requester_id` would be NULL. Fix: add `COALESCE(sc.requester_id, po.requester_id) as requester_id` to the SELECT, or read `po["requester_id"]` separately.
4. The `to_ids` at line 72 uses this `requester_id`. For independent FC PO, `po.requester_id` is already the owner, so reading from `po.*` works as long as we use `COALESCE`.

**`monthly.py`** — same fixes:
1. Check the JOIN pattern with `sc_records` — if INNER JOIN, change to LEFT JOIN
2. Fix `open_po_amount` calculation for FC POs (same COALESCE pattern as search_pos)
3. The `calloff_totals` subquery (line 78-81) already uses LEFT JOIN — no change needed

**`sender.py`** — builds email content from PO data. The JOIN at line 88 (`JOIN pos po ON po.po_id = gr.po_id`) is fine (traces through GRs). But line 121 reads PO data with `JOIN sc_records` — if used for independent FC POs, needs LEFT JOIN. For `entity_type == "po"` (line 108), `_attach_child_grs` is called — for independent FC PO, GRs don't exist, so this produces empty GR list. That's correct behavior. However, the email template at `templates.py:108` lists `sc_id` in `_PO_ORDER` — for independent FC PO this will be blank. Acceptable — just renders as empty cell.

**`schedules.py`** — custom schedule cron (lines 34-37): `JOIN sc_records sc ON sc.sc_id = po.sc_id` (INNER JOIN). Independent FC POs' custom schedules are excluded from processing. Additionally, `sc.requester_id` (line 34) is used for recipient list at line 57. Fix: LEFT JOIN + `COALESCE(sc.requester_id, po.requester_id) as requester_id`.

**`notification_service.py`** — `queue_status_change` for "po" entity_type (line ~96): This function handles SC-triggered notification transitions. PO lifecycle events (create/submit/finish/recall) all pass requester_id via context dict and are already guarded by `if sc else {}`. No changes needed here. However, verify that `get_entity_config` (config.py:14) works with null sc_id — it queries `notification_config WHERE entity_id = ?`, which uses `po_id` directly. Fine.

---

### api/bridge.py

**New endpoint: `get_po_detail`**

Currently, PO detail is loaded via `get_sc_detail({ sc_id })` and the PO is extracted from `sc_detail.pos`. Independent FC PO has no SC, so this doesn't work. A new API endpoint is needed:

```python
def get_po_detail(self, payload) -> dict:
    po_id = _require_payload_field(payload, "po_id")
    with connect(self.config) as conn:
        po = conn.execute(
            """select po.*, v.vendor_name,
               coalesce(po.request_type, sc.request_type) as sc_request_type
               from pos po
               left join sc_records sc on sc.sc_id = po.sc_id
               join vendors v on v.vendor_id = po.vendor_id
               where po.po_id = ?""",
            (po_id,),
        ).fetchone()
        if po is None:
            raise NotFound(f"PO not found: {po_id}")
        po = _row_to_dict(po)

        # Fetch operations records for this PO
        ops = conn.execute(
            "select * from operation_records where object_type = 'po' and object_id = ?",
            (po_id,),
        ).fetchall()

        # Fetch call-off SCs if FC PO
        calloff_scs = []
        if po.get("sc_request_type") == "FC":
            calloff_scs = conn.execute(
                "select * from sc_records where calloff_po_id = ?",
                (po_id,),
            ).fetchall()

        # Permissions: based on PO requester (not SC requester)
        user_id = get_user_by_machine_id(self.config, get_7_digit_id())["user_id"]
        is_owner = po["requester_id"] == user_id
        is_admin = user_is_admin(self.config, user_id)
        permissions = {
            "can_manage_po": is_owner or is_admin,
            "can_manage_gr": False if po.get("sc_request_type") == "FC" else (is_owner or is_admin),
            "can_delete_po": is_owner or is_admin,
        }

        return ok({
            "po": po,
            "calloff_scs": [_row_to_dict(s) for s in calloff_scs],
            "operation_records": [_row_to_dict(o) for o in ops],
            "permissions": permissions,
        })
```

**`get_sc_detail`**: The existing endpoint works for SC-bound POs. For independent FC POs (which aren't under any SC), it naturally won't include them — correct.

**`add_attachments`**: When `parent_sc_id` is null (independent FC PO), resolve the attachment directory to `attachments/po/{po_id}/` instead of `attachments/sc/{sc_id}/po/{po_id}/`.

**`search_pos`**: `is_fc_po` filter must match `pos.request_type = 'FC' OR sc.request_type = 'FC'`.

**`get_po`** (existing helper used by deep links in main.js): Already exists? Check — if it's a standalone endpoint, ensure it returns `request_type` in the result so the frontend can determine the type.

**Download template**: See import_service.py section above for full changes.

**`save_po_notification_config`** (line 749) and **`save_po_custom_schedules`** (line 780): Both use INNER JOIN `pos JOIN sc_records sc ON sc.sc_id = po.sc_id` to look up `sc.requester_id` for permission check. For independent FC PO, the query returns nothing → `NotFound("PO not found")`. Fix: change to LEFT JOIN, then:
```
if not po:
    raise NotFound("PO not found")
requester_id = po["requester_id"]  # may be po.requester_id directly for independent FC PO
# If sc.requester_id is not None (SC-bound PO), use sc's requester; else use PO's requester
if current_user["role"] != "admin" and current_user["user_id"] != requester_id:
    raise PermissionDenied(...)
```
OR: do a two-step check — first query `pos` alone for existence + `requester_id`, then conditionally join SC for permission. Simpler approach: query `pos` alone, then if `po.sc_id` is set, look up SC requester as secondary check. For independent FC PO, use `po.requester_id` directly.

---

## Frontend Changes

### New Route

**`router/index.js`**: Add a route for independent PO detail:
```js
{
  path: '/po/:poId',
  name: 'po-detail-independent',
  component: () => import('@/views/PoDetailView.vue'),
  meta: { layout: 'default', title: 'PO Detail' }
}
```

The existing `/sc/:scId/po/:poId` route is unchanged. Both routes use the same `PoDetailView` component, which detects its mode from the presence/absence of `route.params.scId`.

### PoDetailView — Data Loading Overhaul

Current state: ALL data comes from `get_sc_detail(scId)` via `useSc.fetchDetail(scId)`. For independent FC PO, `scId` is undefined and `scDetail` is empty — everything breaks.

**Required changes:**

1. **`scId` → optional**: Detect mode from `route.params.scId`:
   ```
   const hasSc = computed(() => !!route.params.scId)
   ```

2. **Data loading** (onMounted): Conditionally call `get_sc_detail` or `get_po_detail`:
   ```
   if (hasSc.value) {
       await fetchDetail(scId.value)
   } else {
       const result = await callApi('get_po_detail', { po_id: poId.value })
       poDetailData.value = result
       activeUsers.value = result.active_users || []
       calloffScs.value = result.calloff_scs || []
   }
   ```

3. **`po` computed** (line 238-241): For SC-bound, extract from `scDetail.pos`. For independent, use `poDetailData.po` directly.

4. **`grs` computed** (line 243-246): For independent FC PO, always empty `[]` (GRs can't exist under FC PO). The existing filter `scDetail.grs` also returns `[]` when empty.

5. **`scVendors` computed** (line 247): For independent FC PO, load all active vendors via `searchVendors()` (already called in onMounted). No SC-filtered vendor list.

6. **`poOperationRecords` computed** (line 249-252): For independent FC PO, read from `poDetailData.operation_records`.

7. **`isRequester` computed** (line 253): For independent FC PO, compare with `po.requester_id` instead of `sc.sc.requester_id`:
   ```
   const isRequester = computed(() => {
       if (hasSc.value) return window.__currentUser?.user_id === scDetail.value?.sc?.requester_id
       return window.__currentUser?.user_id === po.value?.requester_id
   })
   ```

8. **`isFcPo` computed** (line 242): Check both `po.request_type` and `po.sc_request_type` (backend returns effective type).

9. **Permissions**: Build a local permissions object instead of relying on `scDetail.permissions`:
   - For SC-bound: existing `scDetail.permissions` (unchanged)
   - For independent: compute from `isRequester || isAdmin`

10. **Buttons gated on permissions** (lines 9-17, 28, 31, 93): Use the unified permissions object. Key mappings:
    - Edit/Submit/Finish: `permissions.can_manage_po`
    - Delete: `permissions.can_delete_po`
    - Add GR: `permissions.can_manage_gr && !isFcPo`
    - New Call-off SC: `permissions.can_manage_po && isFcPo`

11. **SC info section** (lines 36-41): Hide entirely when `!hasSc`. Show PO's own requester info instead (from `po.requester_id`).

12. **Delete redirect** (line 344): For independent FC PO, redirect to `/po` (PO list). For SC-bound, keep existing `/sc/${scId}`.

13. **14 `fetchDetail(scId.value)` calls**: Every post-action refresh must branch:
    ```
    if (hasSc.value) {
        await fetchDetail(scId.value)
    } else {
        const result = await callApi('get_po_detail', { po_id: poId.value })
        // update local state
    }
    ```

14. **GR detail navigation** (lines 79-80): Independent FC PO has no GRs (section hidden). But guard `scId` anyway: if null, use `/po/${poId}/gr/${grId}` or disable navigation.

15. **`parent-sc-id` in AttachmentList** (line 118), **attachment uploads** (lines 308, 474, 484, 499, 504): Pass null when `!hasSc`.

### PoListView — Create PO Dropdown

**"New PO" button** becomes a split-button/dropdown:
- **New Regular PO** → existing SC selection dialog → PoFormDialog (sc_id required)
- **New FC PO** → PoFormDialog directly (sc_id hidden, request_type fixed to "FC")

**`openCreatePoDialog`**: Split into two:
- `openCreateRegularPo()`: existing logic (SC selection dialog)
- `openCreateFcPo()`: skip SC selection, load all vendors, open PoFormDialog directly

**`handlePoSave` / `handlePoSaveDraft`**: For independent FC PO:
- Omit `sc_id` from payload
- Add `request_type: 'FC'` to payload
- Skip `selectedScRecord` (it's null)
- `parent_sc_id` for attachments: pass null

**Detail navigation** (line 29 in PoTable click handler): Branch on `row.sc_id`:
```
if (row.sc_id) {
    $router.push(`/sc/${row.sc_id}/po/${row.po_id}`)
} else {
    $router.push(`/po/${row.po_id}`)
}
```

### PoFormDialog

| Field | Regular PO | Independent FC PO |
|---|---|---|
| SC selection | Pre-filled from SC dialog | Hidden |
| request_type | Hidden (from SC) | Hidden (fixed "FC") |
| vendor | Filtered by SC's vendors | All active vendors |
| requester | Reuse current_user.user_id | Default: current user, not editable in form |
| cost_center | Inherited from SC, editable | Manual input |
| Other fields | Unchanged | Unchanged |

No `sc_id` field needed in the form — it's managed by the parent (PoListView).

### PoTable

- `sc_id` column: `shortId(null)` returns `'-'` already. Tooltip disabled when `!row.sc_id`. No change needed.
- Type column (line 34): `row.sc_request_type === 'FC'` — works for both SC-derived and independent FC PO if backend returns effective type via COALESCE.

### AppHeader — Breadcrumbs

For `po-detail-independent` route (or when `params.scId` is undefined):
```
PO List → PO Detail
```
Instead of:
```
SC List → SC Detail → PO Detail
```

### main.js — Deep Links

Line 22-24: After `get_po({ po_id })`, branch on `po.sc_id`:
```js
if (po.sc_id) {
    router.push(`/sc/${po.sc_id}/po/${params.id}`)
} else {
    router.push(`/po/${params.id}`)
}
```

### HomeView — Workbench PO Clicks

Lines 112, 134: Branch on `row.sc_id`:
```
if (row.sc_id) {
    $router.push(`/sc/${row.sc_id}/po/${row.po_id}`)
} else {
    $router.push(`/po/${row.po_id}`)
}
```

GR clicks (line 175): GRs are always under a call-off SC with valid sc_id — no change needed.

### GrDetailView

No changes needed. GR detail always has a non-null `scId` from the call-off SC. The parent PO link uses that scId correctly.

### ScDetailView

No changes needed. Independent FC POs have no SC parent and won't appear here.

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

### GR creation under FC PO — defense in depth

- **`create_gr`**: Rejects FC POs (both `pos.request_type = 'FC'` and SC-derived FC) before any SC join.
- **All other GR operations**: Include FC gate at entry. If a GR somehow exists under an FC PO, produce a clear error instead of cryptic `sc:None` lock or `NotFound("SC not found: None")`.

### Visibility

- Independent FC PO is visible to its requester and all admins.
- For non-admin users, `_sc_visibility_clauses` in `search_pos` must include a `(po.sc_id IS NULL AND po.requester_id = ?)` fallback.

### Vendor constraints

Independent FC PO has no SC vendor restrictions — vendor is freely chosen from all active vendors. Call-off SCs under the FC PO follow their own vendor linking rules. `vendor_service.py` requires zero changes.

---

## Confirmed: No Changes Needed

| Module | Reason |
|---|---|
| `vendor_service.py` | All vendor operations are SC-agnostic. PO-vendor checks are in po_service.py and correctly gated. |
| `search_grs` in `query_service.py` | GRs trace through call-off SCs (non-null sc_id). INNER JOIN is fine. |
| `GrDetailView.vue` | Parent PO link always has non-null scId from call-off SC. |
| `ScDetailView.vue` | Independent FC PO has no SC parent. Not affected. |
| `notification/templates.py` | PO field order includes `sc_id` which renders as empty for independent FC PO. Cosmetic — acceptable. |
| `_build_sc_cascade` in export | Naturally excludes independent FC POs (they have no SC). Correct behavior. |
| `_build_gr_rows` in export | Handles null sc_id gracefully (produces empty sc_no). |

---

## Edge Cases

1. **Existing data**: all existing POs have `sc_id` set. Migration makes `sc_id` nullable but doesn't change existing data. `request_type` is null for all existing POs (type derived from SC as before).

2. **sc_id immutability**: `sc_id` cannot be changed after creation. The `update_po` allowed fields list does not include `sc_id`.

3. **Lock contention**: independent FC PO uses `po:{po_id}` lock key (in `create_po`). In submit/finish/recall/delete/update, lock key branches: `sc:{sc_id}` when sc_id present, `po:{po_id}` when null.

4. **PO(FC) transferred to another requester**: not supported in current system. If added later, independent FC PO owner check must be updated alongside SC-bound PO owner check.

5. **Vendor-SC consistency**: call-off SCs under independent FC PO can have different vendors from the PO(FC). This is consistent with existing FC behavior.

6. **Two-level nesting**: independent FC PO still respects the two-level limit — call-off SCs cannot be FC type, preventing deeper nesting.

7. **GR operations lock safety**: GRs can only exist under call-off SCs, which always have non-null sc_id. Lock key `sc:{sc_id}` is always valid. FC gate at `create_gr` is the sole enforcement point.

8. **SC visibility for independent FC PO**: The `_sc_visibility_clauses` at `search_pos` line 379 filters out independent FC POs for non-admin users (sc columns are NULL). Fixed by OR clause with `po.requester_id`.

9. **Threshold notifications for independent FC PO**: INNER JOIN in `thresholds.py` excludes them. Fixed by LEFT JOIN + COALESCE for FC type detection.

10. **Workbench COUNT/ROWS mismatch**: Without LEFT JOIN fix, COUNT includes independent FC POs but detail ROWS exclude them. Fixed by LEFT JOIN.