# Framework Contract Call-off Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add framework-contract (FC) call-off layer: SC(FC) → PO(FC) → call-off SC → PO → GR, with full budget cascade and display.

**Architecture:** Single new column `calloff_po_id` on `sc_records` linking child SC to parent PO(FC). PO type derived from parent SC's `request_type`. Budget enforced at each layer with existing patterns. Frontend conditionally renders FC vs regular UI.

**Tech Stack:** Python 3.x (backend services), Vue 3 + Element Plus (frontend), SQLite (database)

---

### Task 1: Database Migration v31

**Files:**
- Modify: `sc_gr_app/db/migrations.py`

- [ ] **Step 1: Bump SCHEMA_VERSION and add _migrate_v31 function**

Open `sc_gr_app/db/migrations.py`. Change line 9:

```python
SCHEMA_VERSION = 30
```

to:

```python
SCHEMA_VERSION = 31
```

Add the migration function before the `migrate` function definition (after `_migrate_v30`):

```python
def _migrate_v31(conn) -> None:
    """Add calloff_po_id column to sc_records for framework-contract call-off SCs."""
    if _table_exists(conn, "sc_records"):
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(sc_records)")}
        if "calloff_po_id" not in existing:
            conn.execute("ALTER TABLE sc_records ADD COLUMN calloff_po_id TEXT REFERENCES pos(po_id)")
    _record(conn, 31)
```

Add the migration call in the `migrate` function. After the v30 block (after line 1491), add:

```python
            if 31 not in _applied_versions(conn):
                conn.execute("BEGIN")
                _migrate_v31(conn)
                conn.commit()
```

- [ ] **Step 2: Run migration to verify**

Run: `python -c "from sc_gr_app.config import AppConfig; from sc_gr_app.db.migrations import migrate; c = AppConfig(); migrate(c); print('Migration v31 OK')"`

Expected: "Migration v31 OK" with no errors.

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/db/migrations.py
git commit -m "feat: add calloff_po_id column to sc_records (migration v31)"
```

---

### Task 2: Budget Service — FC Budget Functions

**Files:**
- Modify: `sc_gr_app/services/budget_service.py`
- Test: `tests/test_budget_service.py`

- [ ] **Step 1: Add `compute_po_fc_budget` function**

Add before the existing `compute_po_budget_decimal` function:

```python
def compute_po_fc_budget_decimal(config: AppConfig, po_id: str) -> dict[str, Decimal]:
    """Compute budget for an FC PO: call-off SC allocation + downstream GR trace."""
    with connect(config) as conn:
        po = conn.execute(
            "select po_amount, sc_id from pos where po_id = ?",
            (po_id,),
        ).fetchone()
        if po is None:
            raise NotFound(f"PO not found: {po_id}")

        sc = conn.execute(
            "select request_type from sc_records where sc_id = ?",
            (po["sc_id"],),
        ).fetchone()
        if sc is None or sc["request_type"] != "FC":
            raise ValidationError("PO is not an FC PO")

        calloff_totals = conn.execute(
            """
            select
              coalesce(sum(sc_amount), 0) as allocated_calloff,
              coalesce(sum(case when status in ('manager_confirm', 'pending', 'approved')
                           then sc_amount else 0 end), 0) as pending_calloff
            from sc_records
            where calloff_po_id = ?
            """,
            (po_id,),
        ).fetchone()

        gr_totals = conn.execute(
            """
            select
              coalesce(sum(case when gr.status in ('pending', 'manager_confirm')
                           then gr.estimated_amount else 0 end), 0) as pending_total,
              coalesce(sum(case when gr.status = 'approved'
                           then gr.con_value else 0 end), 0) as con_value_total,
              coalesce(sum(case when gr.status in ('pending', 'manager_confirm')
                           then coalesce(gr.gross_cost, gr.estimated_amount)
                           else 0 end), 0) as pending_total_incl_tax
            from gr_requests gr
            join pos p on p.po_id = gr.po_id
            join sc_records child_sc on child_sc.sc_id = p.sc_id
            where child_sc.calloff_po_id = ?
            """,
            (po_id,),
        ).fetchone()

    po_amount = _decimal_or_zero(po["po_amount"])
    allocated_calloff = _decimal_or_zero(calloff_totals["allocated_calloff"])
    pending_calloff = _decimal_or_zero(calloff_totals["pending_calloff"])

    return {
        "po_amount": po_amount,
        "allocated_calloff_amount": allocated_calloff,
        "pending_calloff_amount": pending_calloff,
        "open_po_amount": po_amount - allocated_calloff,
        "downstream_consumed": _decimal_or_zero(gr_totals["con_value_total"]),
        "downstream_pending_gr": _decimal_or_zero(gr_totals["pending_total"]),
        "downstream_pending_gr_tax": _decimal_or_zero(gr_totals["pending_total_incl_tax"]),
    }


def compute_po_fc_budget(config: AppConfig, po_id: str) -> dict[str, float]:
    return _decimal_budget_to_float(compute_po_fc_budget_decimal(config, po_id))
```

- [ ] **Step 2: Add `compute_sc_fc_budget` function**

Add after the `compute_po_fc_budget` function:

```python
def compute_sc_fc_budget_decimal(config: AppConfig, sc_id: str) -> dict[str, Decimal]:
    """Compute budget for an SC(FC): PO(FC) allocation + downstream call-off + GR trace."""
    with connect(config) as conn:
        sc = conn.execute(
            "select sc_amount, request_type from sc_records where sc_id = ?",
            (sc_id,),
        ).fetchone()
        if sc is None:
            raise NotFound(f"SC not found: {sc_id}")
        if sc["request_type"] != "FC":
            raise ValidationError("SC is not an FC-type SC")

        po_totals = conn.execute(
            """
            select coalesce(sum(po_amount), 0) as allocated_po
            from pos where sc_id = ?
            """,
            (sc_id,),
        ).fetchone()

        calloff_totals = conn.execute(
            """
            select
              coalesce(sum(child_sc.sc_amount), 0) as downstream_calloff,
              coalesce(sum(case when child_sc.status in ('manager_confirm', 'pending', 'approved')
                           then child_sc.sc_amount else 0 end), 0) as pending_calloff
            from sc_records child_sc
            join pos fc_po on fc_po.po_id = child_sc.calloff_po_id
            where fc_po.sc_id = ?
            """,
            (sc_id,),
        ).fetchone()

        gr_totals = conn.execute(
            """
            select
              coalesce(sum(case when gr.status in ('pending', 'manager_confirm')
                           then gr.estimated_amount else 0 end), 0) as pending_total,
              coalesce(sum(case when gr.status = 'approved'
                           then gr.con_value else 0 end), 0) as con_value_total,
              coalesce(sum(case when gr.status in ('pending', 'manager_confirm')
                           then coalesce(gr.gross_cost, gr.estimated_amount)
                           else 0 end), 0) as pending_total_incl_tax
            from gr_requests gr
            join pos p on p.po_id = gr.po_id
            join sc_records child_sc on child_sc.sc_id = p.sc_id
            join pos fc_po on fc_po.po_id = child_sc.calloff_po_id
            where fc_po.sc_id = ?
            """,
            (sc_id,),
        ).fetchone()

    sc_amount = _decimal_or_zero(sc["sc_amount"])

    return {
        "sc_amount": sc_amount,
        "allocated_po_amount": _decimal_or_zero(po_totals["allocated_po"]),
        "unallocated_sc_amount": sc_amount - _decimal_or_zero(po_totals["allocated_po"]),
        "downstream_calloff_amount": _decimal_or_zero(calloff_totals["downstream_calloff"]),
        "pending_calloff_amount": _decimal_or_zero(calloff_totals["pending_calloff"]),
        "downstream_consumed": _decimal_or_zero(gr_totals["con_value_total"]),
        "downstream_pending_gr": _decimal_or_zero(gr_totals["pending_total"]),
        "downstream_pending_gr_tax": _decimal_or_zero(gr_totals["pending_total_incl_tax"]),
    }


def compute_sc_fc_budget(config: AppConfig, sc_id: str) -> dict[str, float]:
    return _decimal_budget_to_float(compute_sc_fc_budget_decimal(config, sc_id))
```

- [ ] **Step 3: Write tests**

Append to `tests/test_budget_service.py`:

```python
def test_compute_po_fc_budget_no_calloffs(setup_db, sample_users):
    """FC PO with no call-off SCs: open = full PO amount."""
    config, sc_id, po_id = _create_fc_chain(setup_db, sample_users, sc_amount=100000, po_amount=80000)
    budget = compute_po_fc_budget(config, po_id)
    assert budget["po_amount"] == 80000.0
    assert budget["allocated_calloff_amount"] == 0.0
    assert budget["open_po_amount"] == 80000.0
    assert budget["downstream_consumed"] == 0.0


def test_compute_po_fc_budget_with_calloffs(setup_db, sample_users):
    """FC PO with call-off SCs: open reflects allocated amount."""
    config, sc_id, po_id = _create_fc_chain(setup_db, sample_users, sc_amount=100000, po_amount=80000)
    # Create call-off SCs via service
    from sc_gr_app.services.sc_service import create_sc
    calloff1 = create_sc(config, sample_users["admin"], {
        "requester_id": sample_users["requester"]["user_id"],
        "request_type": "material",
        "cost_center": 1000,
        "sc_amount": 30000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
        "calloff_po_id": po_id,
    })
    calloff2 = create_sc(config, sample_users["admin"], {
        "requester_id": sample_users["requester"]["user_id"],
        "request_type": "service",
        "cost_center": 1000,
        "sc_amount": 20000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
        "calloff_po_id": po_id,
    })
    budget = compute_po_fc_budget(config, po_id)
    assert budget["allocated_calloff_amount"] == 50000.0
    assert budget["open_po_amount"] == 30000.0


def test_compute_po_fc_budget_rejects_non_fc_po(setup_db, sample_users):
    """Calling FC budget on a regular PO raises ValidationError."""
    config = setup_db
    from sc_gr_app.services.sc_service import create_sc
    sc = create_sc(config, sample_users["admin"], {
        "requester_id": sample_users["requester"]["user_id"],
        "request_type": "material",
        "cost_center": 1000,
        "sc_amount": 50000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
    })
    from sc_gr_app.services.po_service import create_po
    po = create_po(config, sample_users["admin"], {
        "sc_id": sc["sc_id"],
        "vendor_id": "V-001",
        "po_amount": 30000,
    })
    with pytest.raises(ValidationError, match="not an FC PO"):
        compute_po_fc_budget(config, po["po_id"])


def test_compute_sc_fc_budget(setup_db, sample_users):
    """SC(FC) budget: full downstream trace."""
    config, sc_id, po_id = _create_fc_chain(setup_db, sample_users, sc_amount=100000, po_amount=80000)
    budget = compute_sc_fc_budget(config, sc_id)
    assert budget["sc_amount"] == 100000.0
    assert budget["allocated_po_amount"] == 80000.0
    assert budget["unallocated_sc_amount"] == 20000.0
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_budget_service.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/services/budget_service.py tests/test_budget_service.py
git commit -m "feat: add compute_po_fc_budget and compute_sc_fc_budget functions"
```

---

### Task 3: SC Service — Call-off SC CRUD

**Files:**
- Modify: `sc_gr_app/services/sc_service.py`

- [ ] **Step 1: Add call-off PO validation helper**

Add after the `REQUIRED_BUSINESS_FIELDS` definition (after line 63):

```python
def _validate_calloff_po(conn, calloff_po_id: str | None, request_type: str | None, sc_amount) -> None:
    """Validate call-off PO reference for call-off SC creation/submit."""
    if calloff_po_id is None:
        if request_type == "FC":
            return
        return

    if request_type == "FC":
        raise ValidationError("Call-off SC cannot have request_type 'FC'")

    po_row = conn.execute(
        """select po.po_id, po.po_amount, po.status, sc.request_type as parent_sc_type
           from pos po
           join sc_records sc on sc.sc_id = po.sc_id
           where po.po_id = ?""",
        (calloff_po_id,),
    ).fetchone()
    if po_row is None:
        raise NotFound(f"PO not found: {calloff_po_id}")
    if po_row["parent_sc_type"] != "FC":
        raise ValidationError("Call-off PO must belong to an FC-type SC")
    if po_row["status"] != "active":
        raise ConflictError("Call-off PO must be active to create call-off SCs")

    calloff_total = conn.execute(
        "select coalesce(sum(sc_amount), 0) from sc_records where calloff_po_id = ?",
        (calloff_po_id,),
    ).fetchone()[0]
    new_amount = Decimal(str(sc_amount)) if sc_amount is not None else Decimal("0")
    if Decimal(str(calloff_total)) + new_amount > Decimal(str(po_row["po_amount"])):
        raise ConflictError("Call-off SC total would exceed PO(FC) amount")
```

- [ ] **Step 2: Modify `create_sc` to support `calloff_po_id`**

In `create_sc`, after the `_require_fields(data, REQUIRED_FIELDS)` call, add before `if operation_mode == "normal":`:

```python
    calloff_po_id = data.get("calloff_po_id")
    if calloff_po_id is not None and data["request_type"] == "FC":
        raise ValidationError("Call-off SC cannot have request_type 'FC'")
```

And change the INSERT to include `calloff_po_id`. Add the column to the INSERT statement after `internal_system_number` and before `currency`:

Find the INSERT in create_sc (approx line 438) and add `calloff_po_id` to the column list and values:

In the INSERT columns, add `calloff_po_id` and in VALUES add `data.get("calloff_po_id")`.

- [ ] **Step 3: Modify `create_sc_draft` to validate `calloff_po_id`**

In `create_sc_draft`, add a validation call before the INSERT. After `_require_fields(data, ("requester_id",))`, add:

```python
    calloff_po_id = data.get("calloff_po_id")
```

Then inside the `with connect(config) as conn:` block, before the INSERT, add budget validation:

```python
                if calloff_po_id is not None:
                    _validate_calloff_po(conn, calloff_po_id, data.get("request_type"), data.get("sc_amount"))
```

And add `calloff_po_id` to the INSERT column list and values. In the VALUES tuple, add `data.get("calloff_po_id")` at the end (before the final params).

- [ ] **Step 4: Modify `submit_sc` to validate call-off constraints**

In `submit_sc`, after the existing permission check, add:

```python
                calloff_po_id = before.get("calloff_po_id")
                if calloff_po_id is not None:
                    _validate_calloff_po(conn, calloff_po_id, merged.get("request_type"), merged["sc_amount"])
```

- [ ] **Step 5: Modify `update_sc` for call-off specific checks**

In `update_sc`, the existing `_validate_sc_amount_not_below_usage` call handles the PO/GR usage check. For call-off SCs, also validate against PO(FC) remaining. After the `_validate_sc_amount_not_below_usage` call, add:

```python
                calloff_po_id = before.get("calloff_po_id")
                if calloff_po_id is not None and "sc_amount" in allowed:
                    po_row = conn.execute(
                        "select po_amount from pos where po_id = ?",
                        (calloff_po_id,),
                    ).fetchone()
                    if po_row:
                        sibling_total = conn.execute(
                            "select coalesce(sum(sc_amount), 0) from sc_records "
                            "where calloff_po_id = ? and sc_id != ?",
                            (calloff_po_id, sc_id),
                        ).fetchone()[0]
                        if Decimal(str(sibling_total)) + Decimal(str(merged["sc_amount"])) > Decimal(str(po_row["po_amount"])):
                            raise ConflictError("Call-off SC total would exceed PO(FC) amount")
```

- [ ] **Step 6: Modify `finish_sc` for FC-type SCs**

The existing `finish_sc` already blocks if any POs are not finished. This covers FC POs under SC(FC). No change needed — existing logic handles this.

- [ ] **Step 7: Modify `recall_sc` for call-off SCs**

The existing recall check blocks if any non-draft POs exist. This is sufficient. No change needed.

- [ ] **Step 8: Modify `get_sc_detail` to include budget and call-off info**

In `get_sc_detail`, after computing PO budget (line 1173), modify the return to include the appropriate budget:

```python
    sc = _get_sc(conn, sc_id)
    _assert_can_view_sc(current_user, sc)

    if sc["request_type"] == "FC":
        sc_budget = compute_sc_fc_budget(config, sc_id)
    else:
        sc_budget = compute_sc_budget(config, sc_id)

    # For call-off SCs, include parent PO(FC) info
    parent_po = None
    if sc.get("calloff_po_id"):
        parent_po_row = conn.execute(
            """select po.*, sc.request_type as parent_sc_type
               from pos po
               join sc_records sc on sc.sc_id = po.sc_id
               where po.po_id = ?""",
            (sc["calloff_po_id"],),
        ).fetchone()
        if parent_po_row:
            parent_po = _row_to_dict(parent_po_row)
            parent_po["fc_budget"] = compute_po_fc_budget(config, sc["calloff_po_id"])

    return {
        "sc": sc,
        "budget": sc_budget,
        "pos": pos,
        "grs": grs,
        "operation_records": records,
        "permissions": _sc_permissions(current_user, sc),
        "vendors": _fetch_sc_vendors(conn, sc_id),
        "parent_po": parent_po,
    }
```

- [ ] **Step 8b: Fix per-PO budget computation in `get_sc_detail` for FC POs**

In `get_sc_detail`, the existing loop at line ~1173 computes `compute_po_budget` for every PO. Change to branch on SC type:

```python
    for po in pos:
        if sc["request_type"] == "FC":
            po_budget = compute_po_fc_budget(config, po["po_id"])
            po["open_po_amount"] = po_budget["open_po_amount"]
            po["allocated_calloff_amount"] = po_budget["allocated_calloff_amount"]
            po["pending_calloff_amount"] = po_budget["pending_calloff_amount"]
            po["downstream_consumed"] = po_budget["downstream_consumed"]
            po["downstream_pending_gr"] = po_budget["downstream_pending_gr"]
            po["downstream_pending_gr_tax"] = po_budget["downstream_pending_gr_tax"]
        else:
            po["budget"] = compute_po_budget(config, po["po_id"])
            po["open_po_amount"] = po["budget"]["open_po_amount"]
            po["consumed_amount"] = po["budget"]["po_con_value_total"]
            po["pending_total"] = po["budget"]["po_pending_total"]
            po["pending_total_incl_tax"] = po["budget"]["po_pending_total_incl_tax"]
```

Add the import for `compute_po_fc_budget` at the top:

```python
from sc_gr_app.services.budget_service import (
    compute_po_budget,
    compute_po_fc_budget,
    compute_sc_budget,
    compute_sc_fc_budget,
)
```

- [ ] **Step 8c: Also include `sc_request_type` in PO objects returned by `get_sc_detail`**

In the PO query in `get_sc_detail`, replace the existing JOIN with one that includes `sc.request_type`:

```python
        pos = [
            _row_to_dict(row)
            for row in conn.execute(
                """select po.*, v.vendor_name, v.ksrm_vendor_code,
                   sc.request_type as sc_request_type
                   from pos po
                   join vendors v on v.vendor_id = po.vendor_id
                   join sc_records sc on sc.sc_id = po.sc_id
                   where po.sc_id = ?
                   order by po.created_at, po.po_id""",
                (sc_id,),
            )
        ]
```

This ensures `sc_request_type` is available on each PO object for frontend conditional rendering.

- [ ] **Step 9: Run existing tests to check for regressions**

Run: `pytest tests/test_sc_po_gr_flow.py tests/test_budget_service.py -v`
Expected: all tests pass.

- [ ] **Step 10: Commit**

```bash
git add sc_gr_app/services/sc_service.py
git commit -m "feat: add call-off SC CRUD support in sc_service"
```

---

### Task 4: PO Service — FC PO Behavior

**Files:**
- Modify: `sc_gr_app/services/po_service.py`

- [ ] **Step 1: Add call-off SC count check for PO(FC) finish**

In `finish_po`, after the existing status check `if before["status"] != "active":`, add FC-specific check before the GR check:

```python
                parent_sc = conn.execute(
                    "select request_type from sc_records where sc_id = ?",
                    (before["sc_id"],),
                ).fetchone()

                if parent_sc and parent_sc["request_type"] == "FC":
                    non_final_calloffs = conn.execute(
                        """
                        SELECT sc_id, status FROM sc_records
                        WHERE calloff_po_id = ? AND status NOT IN ('finished', 'denied')
                        """,
                        (po_id,),
                    ).fetchall()
                    if non_final_calloffs:
                        raise ConflictError(
                            f"Cannot finish PO: {len(non_final_calloffs)} call-off SC(s) not in final state. "
                            "Finish or deny all call-off SCs first."
                        )
                else:
                    # Existing GR final-state check
                    non_final_grs = conn.execute(...)
```

Wrap the existing GR check in an `else` branch of this `if/else`.

- [ ] **Step 2: Add PO(FC) amount validation on update**

In `update_po`, after the existing `sibling_total` check, add FC-specific validation for downward amount edits:

```python
                if sc["request_type"] == "FC" and "po_amount" in updates:
                    calloff_total = conn.execute(
                        "select coalesce(sum(sc_amount), 0) from sc_records where calloff_po_id = ?",
                        (po_id,),
                    ).fetchone()[0]
                    if po_amount < Decimal(str(calloff_total)):
                        raise ConflictError("PO amount cannot be below allocated call-off SC amounts")
```

- [ ] **Step 3: Modify `recall_po` for FC PO**

Add after the existing `if before["status"] != "active":` check:

```python
                parent_sc = conn.execute(
                    "select request_type from sc_records where sc_id = ?",
                    (before["sc_id"],),
                ).fetchone()
                if parent_sc and parent_sc["request_type"] == "FC":
                    non_draft_calloffs = conn.execute(
                        "select count(*) from sc_records where calloff_po_id = ? and status != 'draft'",
                        (po_id,),
                    ).fetchone()[0]
                    if non_draft_calloffs > 0:
                        raise ConflictError("Cannot recall PO(FC): non-draft call-off SCs exist")
```

Wrap the existing GR non-draft check in an `else` of this block.

- [ ] **Step 4: Delete PO(FC) guard**

In `delete_po`, add after the existing status check:

```python
                parent_sc = conn.execute(
                    "select request_type from sc_records where sc_id = ?",
                    (before["sc_id"],),
                ).fetchone()
                if parent_sc and parent_sc["request_type"] == "FC":
                    calloff_exists = conn.execute(
                        "select 1 from sc_records where calloff_po_id = ? limit 1",
                        (po_id,),
                    ).fetchone()
                    if calloff_exists:
                        raise ConflictError("Cannot delete PO(FC) with existing call-off SCs")
```

- [ ] **Step 5: Run existing PO tests**

Run: `pytest tests/test_po_service.py -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add sc_gr_app/services/po_service.py
git commit -m "feat: add FC PO behavior — finish/update/recall/delete guards"
```

---

### Task 5: GR Service — FC PO Guard

**Files:**
- Modify: `sc_gr_app/services/gr_service.py`

- [ ] **Step 1: Block GR creation under FC POs**

In `create_gr` (find the function), add a check after the PO is fetched. After the `po = conn.execute(...)` line that gets the parent PO, add:

```python
                po = conn.execute(
                    "select * from pos where po_id = ?",
                    (data["po_id"],),
                ).fetchone()
                if po is None:
                    raise NotFound(f"PO not found: {data['po_id']}")

                parent_sc = conn.execute(
                    "select request_type from sc_records where sc_id = ?",
                    (po["sc_id"],),
                ).fetchone()
                if parent_sc and parent_sc["request_type"] == "FC":
                    raise ConflictError("Cannot create GR under an FC PO. Use call-off SCs instead.")
```

- [ ] **Step 2: Commit**

```bash
git add sc_gr_app/services/gr_service.py
git commit -m "feat: block GR creation under FC POs"
```

---

### Task 6: Query Service — New Filters & FC PO Fixes

**Files:**
- Modify: `sc_gr_app/services/query_service.py`

- [ ] **Step 1: Add `calloff_po_id` and `is_calloff` filters to `search_scs`**

Add to both `allowed_filters` and `allowed_sorts`:

```python
# In allowed_filters dict:
"calloff_po_id": "sc.calloff_po_id",
"is_calloff": "sc.calloff_po_id",

# In allowed_sorts dict:
"calloff_po_id": "sc.calloff_po_id",
```

Then in `_append_filters` handling: `is_calloff` is special — it's not a direct column match. Handle it in the `search_scs` function before passing to `_search`:

```python
    if filters and "is_calloff" in filters:
        if filters["is_calloff"] == "1":
            base_clauses.append("sc.calloff_po_id IS NOT NULL")
        elif filters["is_calloff"] == "0":
            base_clauses.append("sc.calloff_po_id IS NULL")
        filters = {k: v for k, v in filters.items() if k != "is_calloff"}
```

And add `calloff_po_id` to the SELECT:

```python
        select_sql="""
        select distinct
          sc.*,
          requester.user_name as requester_name
        from sc_records sc
```

The `sc.*` already includes `calloff_po_id`.

- [ ] **Step 2: Fix `search_pos` open amount for FC POs**

Modify the `search_pos` SELECT to branch on SC type. Replace the `open_po_amount` line in the SELECT:

Change from:
```sql
po.po_amount - coalesce(gr_totals.pending_total, 0)
  - coalesce(gr_totals.con_value_total, 0) as open_po_amount,
```

To:
```sql
case when sc.request_type = 'FC'
  then po.po_amount - coalesce(calloff_totals.allocated, 0)
  else po.po_amount - coalesce(gr_totals.pending_total, 0)
       - coalesce(gr_totals.con_value_total, 0)
end as open_po_amount,
```

And add the calloff subquery to the FROM clause. After the existing `gr_totals` LEFT JOIN, add:

```sql
        left join (
          select calloff_po_id, coalesce(sum(sc_amount), 0) as allocated
          from sc_records
          where calloff_po_id is not null
          group by calloff_po_id
        ) calloff_totals on calloff_totals.calloff_po_id = po.po_id
```

Also add `sc.request_type as sc_request_type` to the SELECT and `is_fc_po` filter:

```python
# In allowed_filters:
"is_fc_po": "sc.request_type",
```

And handle it in `search_pos` before calling `_search`:

```python
    if filters and "is_fc_po" in filters:
        if filters["is_fc_po"] == "1":
            base_clauses.append("sc.request_type = 'FC'")
        elif filters["is_fc_po"] == "0":
            base_clauses.append("sc.request_type != 'FC'")
        filters = {k: v for k, v in filters.items() if k != "is_fc_po"}
```

- [ ] **Step 3: Fix `workbench_data` PO queries for FC POs**

In the `workbench_data` function, modify the PO `open_po_amount` calculation. The current query uses:

```sql
po.po_amount - COALESCE(gr_sums.pending_total, 0)
- COALESCE(gr_sums.con_value_total, 0) AS open_po_amount
```

Replace with:

```sql
CASE WHEN sc.request_type = 'FC'
  THEN po.po_amount - COALESCE(calloff_sums.allocated, 0)
  ELSE po.po_amount - COALESCE(gr_sums.pending_total, 0)
       - COALESCE(gr_sums.con_value_total, 0)
END AS open_po_amount
```

Add the calloff subquery to the FROM clause (alongside `gr_sums`):

```sql
LEFT JOIN (
  SELECT calloff_po_id, SUM(sc_amount) AS allocated
  FROM sc_records WHERE calloff_po_id IS NOT NULL
  GROUP BY calloff_po_id
) calloff_sums ON calloff_sums.calloff_po_id = po.po_id
```

- [ ] **Step 4: Run query tests**

Run: `pytest tests/test_query_service.py tests/test_query_filters.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/services/query_service.py
git commit -m "feat: add FC filters to search_scs/search_pos, fix FC PO open amount"
```

---

### Task 7: Import & Export Services

**Files:**
- Modify: `sc_gr_app/services/import_service.py`
- Modify: `sc_gr_app/services/export_service.py`

- [ ] **Step 1: Add `calloff_po_id` to SC import**

In `import_service.py`, find the SC import row parsing (the function that builds the INSERT). Add `calloff_po_id` to the INSERT column list. In the column-to-index mapping, add:

```python
"calloff_po_id": headers.get("calloff_po_id"),
```

In the INSERT SQL, add the column and a placeholder. If the existing SC import uses column names from the headers, ensure `calloff_po_id` is in the allowed set.

- [ ] **Step 2: Add `calloff_po_id` validation to import**

When `calloff_po_id` is provided in an SC import row, validate:

```python
calloff_po_id = row_data.get("calloff_po_id")
if calloff_po_id:
    po_exists = conn.execute(
        "select 1 from pos po join sc_records sc on sc.sc_id = po.sc_id "
        "where po.po_id = ? and sc.request_type = 'FC'",
        (calloff_po_id,),
    ).fetchone()
    if not po_exists:
        raise ValidationError(f"calloff_po_id {calloff_po_id} is not a valid FC PO")
```

- [ ] **Step 3: Add `calloff_po_id` to SC export**

In `export_service.py`, find the SC export column list. Add `calloff_po_id` to the SC export columns.

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/services/import_service.py sc_gr_app/services/export_service.py
git commit -m "feat: add calloff_po_id to SC import/export"
```

---

### Task 8: Notification Thresholds & Monthly Fix

**Files:**
- Modify: `sc_gr_app/notification/thresholds.py`
- Modify: `sc_gr_app/notification/monthly.py`

- [ ] **Step 1: Fix `thresholds.py` for FC POs**

Find the `check_all_active_pos` or equivalent function. The current query computes `remaining_pct` using `SUM(approved GR con_value)`. Modify to branch on SC type:

```python
rows = conn.execute(
    """
    select po.po_id, po.po_amount, po.sc_id,
           po.po_amount - coalesce(
             case when sc.request_type = 'FC'
               then calloff_totals.allocated
               else gr_totals.con_value_total
             end, 0
           ) as remaining,
           po.po_amount as total
    from pos po
    join sc_records sc on sc.sc_id = po.sc_id
    left join (
      select po_id, sum(con_value) as con_value_total
      from gr_requests where status = 'approved'
      group by po_id
    ) gr_totals on gr_totals.po_id = po.po_id
    left join (
      select calloff_po_id, sum(sc_amount) as allocated
      from sc_records where calloff_po_id is not null
      group by calloff_po_id
    ) calloff_totals on calloff_totals.calloff_po_id = po.po_id
    where po.status = 'active'
    """,
).fetchall()
```

- [ ] **Step 2: Fix `monthly.py` for FC POs**

Find the monthly summary query that computes `open_po_amount`. Apply the same branch-on-SC-type pattern as in `search_pos`:

```sql
case when sc.request_type = 'FC'
  then po.po_amount - coalesce(calloff_totals.allocated, 0)
  else po.po_amount - coalesce(gr_totals.pending_total, 0)
       - coalesce(gr_totals.con_value_total, 0)
end as open_po_amount
```

Add the `calloff_totals` subquery to the monthly summary query.

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/notification/thresholds.py sc_gr_app/notification/monthly.py
git commit -m "fix: FC PO budget math in notification thresholds and monthly summary"
```

---

### Task 9: API Bridge — Import Template & Export Cascade

**Files:**
- Modify: `sc_gr_app/api/bridge.py`

- [ ] **Step 1: Add `calloff_po_id` to SC import template**

In `download_sc_template`, add `calloff_po_id` to the headers list:

```python
headers = ["sc_id", "sc_no", "requester_id", "request_type", "cost_center",
           "sc_amount", "service_period_start", "service_period_end", "status",
           "description", "currency", "internal_system_number", "calloff_po_id"]
```

And add a hint row entry: `"Optional (FC PO ID for call-off SCs)"`.

- [ ] **Step 2: Handle FC PO export cascade**

In the export cascade methods (`export_pos_cascade` or equivalent), when a PO is an FC PO (parent SC request_type = 'FC'), skip the GR sheet and produce a "Call-off SCs" sheet instead with columns: `sc_id, sc_no, request_type, sc_amount, status, created_at`.

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/api/bridge.py
git commit -m "feat: add calloff_po_id to SC import template, FC PO export cascade"
```

---

### Task 10: i18n — New Translation Keys

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.js`
- Modify: `frontend/src/i18n/locales/en-US.js`

- [ ] **Step 1: Add SC-related keys**

In `zh-CN.js`, find the `sc` section (around scId, scNo). Add:

```javascript
    calloffBadge: '外委',
    newCalloffSc: '新建外委 SC',
    calloffPoId: '外委来源 PO',
    allocatedPo: '已分配 PO 总额',
    unallocated: '未分配金额',
    downstreamCalloff: '下游外委 SC',
    pendingCalloff: '进行中外委 SC',
```

In `en-US.js`, add corresponding English keys:

```javascript
    calloffBadge: 'Call-off',
    newCalloffSc: 'New Call-off SC',
    calloffPoId: 'Call-off Source PO',
    allocatedPo: 'Allocated (POs)',
    unallocated: 'Unallocated',
    downstreamCalloff: 'Downstream Call-off SCs',
    pendingCalloff: 'Pending Call-off SCs',
```

- [ ] **Step 2: Add PO-related keys**

In `zh-CN.js`, find the `po` section. Add:

```javascript
    openPoAmountFc: 'PO 可用金额',
    allocatedCalloff: '已分配外委总额',
    pendingCalloff: '进行中外委',
    downstreamConsumed: '下游已验收',
    downstreamPendingGr: '下游待验收 GR',
```

In `en-US.js`:

```javascript
    openPoAmountFc: 'Open PO Amount',
    allocatedCalloff: 'Allocated (Call-off SCs)',
    pendingCalloff: 'Pending Call-off SCs',
    downstreamConsumed: 'Downstream Consumed',
    downstreamPendingGr: 'Downstream Pending GR',
```

- [ ] **Step 3: Add filter keys**

In `zh-CN.js`, find the `filter` section. Add:

```javascript
    isCalloff: '外委 SC',
    isFcPo: 'FC 类型 PO',
```

In `en-US.js`:

```javascript
    isCalloff: 'Call-off SC',
    isFcPo: 'FC PO',
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/i18n/locales/zh-CN.js frontend/src/i18n/locales/en-US.js
git commit -m "feat: add i18n keys for FC call-off feature"
```

---

### Task 11: Frontend — SC List View (Badge, Filter, Create Dropdown)

**Files:**
- Modify: `frontend/src/components/sc/ScTable.vue`
- Modify: `frontend/src/views/HomeView.vue` (or wherever SC list lives)

- [ ] **Step 1: Add call-off badge to SC table**

In `ScTable.vue`, add a badge column or inline indicator. After the `sc_id` or `sc_no` column template, add:

```html
<el-table-column :label="$t('sc.requestType')" width="100">
  <template #default="{ row }">
    <el-tag v-if="row.calloff_po_id" type="warning" size="small">
      {{ $t('sc.calloffBadge') }}
    </el-tag>
    <span v-else>{{ row.request_type }}</span>
  </template>
</el-table-column>
```

- [ ] **Step 2: Add filter for Top-level vs Call-off SC**

In the filter section of the SC list page, add a select/dropdown:

```html
<el-select v-model="scFilters.is_calloff" :placeholder="$t('filter.isCalloff')" clearable @change="fetchScs">
  <el-option label="Top-level SC" value="0" />
  <el-option label="Call-off SC" value="1" />
</el-select>
```

Pass `is_calloff` to the `search_scs` API call.

- [ ] **Step 3: Add Create SC dropdown**

Replace the existing "Create SC" button with a split button or dropdown:

```html
<el-dropdown @command="handleCreateScCommand">
  <el-button type="primary">
    {{ $t('sc.create') }}
    <el-icon><arrow-down /></el-icon>
  </el-button>
  <template #dropdown>
    <el-dropdown-menu>
      <el-dropdown-item command="new">{{ $t('sc.create') }}</el-dropdown-item>
      <el-dropdown-item command="calloff">{{ $t('sc.newCalloffSc') }}</el-dropdown-item>
    </el-dropdown-menu>
  </template>
</el-dropdown>
```

`command="new"` opens the existing SC creation form. `command="calloff"` opens a PO(FC) selector dialog first.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/sc/ScTable.vue frontend/src/views/HomeView.vue
git commit -m "feat: add call-off badge, filter, and create dropdown to SC list"
```

---

### Task 12: Frontend — PO(FC) Selector Dialog

**Files:**
- Create: `frontend/src/components/sc/PoFcSelectorDialog.vue`

- [ ] **Step 1: Create the PO(FC) selector component**

```vue
<template>
  <el-dialog v-model="visible" :title="$t('sc.newCalloffSc')" width="600px">
    <el-table :data="fcPos" @row-click="select" highlight-current-row>
      <el-table-column prop="po_id" :label="$t('po.poId')" width="200" />
      <el-table-column prop="po_no" :label="$t('po.poNo')" width="150" />
      <el-table-column prop="po_amount" :label="$t('po.poAmount')" width="120">
        <template #default="{ row }">
          <AmountDisplay :value="row.po_amount" />
        </template>
      </el-table-column>
      <el-table-column prop="open_po_amount" :label="$t('po.openPoAmountFc')" width="120">
        <template #default="{ row }">
          <AmountDisplay :value="row.open_po_amount" />
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { searchPos } from '@/composables/usePo'

const visible = defineModel('visible', { type: Boolean, default: false })
const emit = defineEmits(['select'])

const fcPos = ref([])

watch(visible, async (val) => {
  if (val) {
    const result = await searchPos({ is_fc_po: '1', status: 'active' })
    fcPos.value = result.rows
  }
})

function select(row) {
  emit('select', row.po_id)
  visible.value = false
}
</script>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/sc/PoFcSelectorDialog.vue
git commit -m "feat: add PO(FC) selector dialog for call-off SC creation"
```

---

### Task 13: Frontend — SC Creation Form (call-off Support)

**Files:**
- Modify: `frontend/src/components/sc/ScFormDialog.vue`

- [ ] **Step 1: Accept `calloffPoId` prop and conditionally render**

Add props:

```javascript
const props = defineProps({
  visible: Boolean,
  sc: { type: Object, default: null },
  calloffPoId: { type: String, default: null },
  calloffPoAmount: { type: Number, default: null },
})
```

When `calloffPoId` is set:
- Show a readonly field displaying the linked PO(FC) ID and remaining amount
- Disable the `request_type` picker's `FC` option
- Set max validation on `sc_amount` to `calloffPoAmount`

```html
<el-form-item v-if="calloffPoId" :label="$t('sc.calloffPoId')">
  <el-input :model-value="calloffPoId" disabled />
  <span v-if="calloffPoAmount !== null">
    {{ $t('po.openPoAmountFc') }}: {{ calloffPoAmount }}
  </span>
</el-form-item>
```

For `request_type`, filter out 'FC' when `calloffPoId` is set:

```javascript
const availableTypes = computed(() => {
  const types = ['material', 'service', 'fixed_asset', 'FC']
  if (props.calloffPoId) return types.filter(t => t !== 'FC')
  return types
})
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/sc/ScFormDialog.vue
git commit -m "feat: add call-off PO context to SC creation form"
```

---

### Task 14: Frontend — SC Detail Budget Section

**Files:**
- Modify: `frontend/src/views/ScDetailView.vue`
- Create: `frontend/src/components/sc/ScBudgetCard.vue`

- [ ] **Step 1: Create ScBudgetCard component**

```vue
<template>
  <el-descriptions :column="3" border size="small" class="sc-budget-descriptions">
    <el-descriptions-item :label="$t('sc.scAmount')">
      <AmountDisplay :value="budget.sc_amount" />
    </el-descriptions-item>
    <el-descriptions-item :label="$t('sc.allocatedPo')">
      <AmountDisplay :value="budget.allocated_po_amount" />
    </el-descriptions-item>
    <el-descriptions-item :label="$t('sc.unallocated')">
      <AmountDisplay :value="budget.unallocated_sc_amount" />
    </el-descriptions-item>

    <template v-if="isFC">
      <el-descriptions-item :label="$t('sc.downstreamCalloff')">
        <AmountDisplay :value="budget.downstream_calloff_amount" />
      </el-descriptions-item>
      <el-descriptions-item :label="$t('sc.pendingCalloff')">
        <AmountDisplay :value="budget.pending_calloff_amount" />
      </el-descriptions-item>
    </template>

    <el-descriptions-item label="Consumed">
      <AmountDisplay :value="budget.sc_con_value_total" />
    </el-descriptions-item>
    <el-descriptions-item label="Pending GR (excl)">
      <AmountDisplay :value="budget.sc_pending_total" />
    </el-descriptions-item>
    <el-descriptions-item label="Pending GR (incl)">
      <AmountDisplay :value="budget.sc_pending_total_incl_tax" />
    </el-descriptions-item>
  </el-descriptions>
</template>

<script setup>
import AmountDisplay from '@/components/common/AmountDisplay.vue'

defineProps({
  budget: { type: Object, required: true },
  isFC: { type: Boolean, default: false },
})
</script>
```

- [ ] **Step 2: Integrate into ScDetailView**

In `ScDetailView.vue`, after the `<ScDetailCard>` component, add:

```html
<ScBudgetCard
  v-if="detail.budget"
  :budget="detail.budget"
  :is-fc="detail.sc.request_type === 'FC'"
/>

<div v-if="detail.parent_po" class="calloff-context">
  <el-descriptions :column="2" border size="small">
    <el-descriptions-item :label="$t('sc.calloffPoId')">
      {{ detail.parent_po.po_id }}
    </el-descriptions-item>
    <el-descriptions-item :label="$t('po.openPoAmountFc')">
      <AmountDisplay :value="detail.parent_po.fc_budget?.open_po_amount" />
    </el-descriptions-item>
  </el-descriptions>
</div>
```

Import `ScBudgetCard`:

```javascript
import ScBudgetCard from '@/components/sc/ScBudgetCard.vue'
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/sc/ScBudgetCard.vue frontend/src/views/ScDetailView.vue
git commit -m "feat: add SC budget summary card and call-off parent context"
```

---

### Task 15: Frontend — PO List FC Badge & Filter

**Files:**
- Modify: `frontend/src/views/HomeView.vue` (PO list tab)

- [ ] **Step 1: Add FC badge to PO table**

In the PO table columns, add a type indicator column:

```html
<el-table-column :label="$t('po.type')" width="80">
  <template #default="{ row }">
    <el-tag v-if="row.sc_request_type === 'FC'" type="info" size="small">FC</el-tag>
    <span v-else>—</span>
  </template>
</el-table-column>
```

- [ ] **Step 2: Add FC PO filter dropdown**

```html
<el-select v-model="poFilters.is_fc_po" :placeholder="$t('filter.isFcPo')" clearable @change="fetchPos">
  <el-option label="FC PO" value="1" />
  <el-option label="Regular PO" value="0" />
</el-select>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/HomeView.vue
git commit -m "feat: add FC badge and filter to PO list"
```

---

### Task 16: Frontend — PO Detail Conditional Rendering

**Files:**
- Modify: `frontend/src/views/PoDetailView.vue`

- [ ] **Step 1: Conditional rendering based on PO type**

In `PoDetailView.vue`, compute `isFcPo`:

```javascript
const isFcPo = computed(() => po.value?.sc_request_type === 'FC' || po.value?.parent_sc_type === 'FC')
```

Use `v-if="!isFcPo"` on GR-related sections (GR record list, create GR button). Use `v-if="isFcPo"` on call-off SC sections.

For the budget display:

```html
<template v-if="!isFcPo">
  <!-- existing regular PO budget -->
  <el-descriptions-item :label="$t('po.poAmount')"><AmountDisplay :value="po.po_amount" /></el-descriptions-item>
  <el-descriptions-item :label="$t('po.openPoAmount')"><AmountDisplay :value="po.open_po_amount" /></el-descriptions-item>
  <el-descriptions-item :label="$t('po.consumedAmount')"><AmountDisplay :value="po.consumed_amount" /></el-descriptions-item>
</template>
<template v-else>
  <!-- FC PO budget -->
  <el-descriptions-item :label="$t('po.poAmount')"><AmountDisplay :value="po.po_amount" /></el-descriptions-item>
  <el-descriptions-item :label="$t('po.openPoAmountFc')"><AmountDisplay :value="po.open_po_amount" /></el-descriptions-item>
  <el-descriptions-item :label="$t('po.allocatedCalloff')"><AmountDisplay :value="po.allocated_calloff_amount" /></el-descriptions-item>
  <el-descriptions-item :label="$t('po.pendingCalloff')"><AmountDisplay :value="po.pending_calloff_amount" /></el-descriptions-item>
  <el-descriptions-item :label="$t('po.downstreamConsumed')"><AmountDisplay :value="po.downstream_consumed" /></el-descriptions-item>
  <el-descriptions-item :label="$t('po.downstreamPendingGr')"><AmountDisplay :value="po.downstream_pending_gr" /></el-descriptions-item>
</template>
```

For the call-off SC list (FC PO):

```html
<div v-if="isFcPo">
  <h3>Call-off SCs</h3>
  <el-table :data="calloffScs">
    <el-table-column prop="sc_id" :label="$t('sc.scId')" />
    <el-table-column prop="sc_no" :label="$t('sc.scNo')" />
    <el-table-column prop="sc_amount" :label="$t('sc.scAmount')" />
    <el-table-column prop="status" :label="$t('sc.status')" />
  </el-table>
  <el-button type="primary" @click="openCalloffScForm">{{ $t('sc.newCalloffSc') }}</el-button>
</div>
```

Load call-off SCs and FC budget:

```javascript
const calloffScs = ref([])
const fcBudget = ref(null)

async function loadCalloffData() {
  if (!isFcPo.value) return
  const result = await callApi('search_scs', { calloff_po_id: po.value.po_id })
  calloffScs.value = result.rows
  fcBudget.value = await callApi('get_po_fc_budget', { po_id: po.value.po_id })
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/PoDetailView.vue
git commit -m "feat: conditional PO detail rendering for FC vs regular POs"
```

---

### Task 17: Integration Test — Full FC Call-off Flow

**Files:**
- Create: `tests/test_fc_calloff_flow.py`

- [ ] **Step 1: Write integration test**

```python
"""Integration tests for FC call-off flow: SC(FC) → PO(FC) → call-off SC → PO → GR."""
import pytest
from sc_gr_app.services.sc_service import create_sc, submit_sc, approve_sc, finish_sc
from sc_gr_app.services.po_service import create_po, submit_po, finish_po
from sc_gr_app.services.gr_service import create_gr
from sc_gr_app.services.budget_service import compute_po_fc_budget, compute_sc_fc_budget
from sc_gr_app.errors import ConflictError


def test_full_fc_calloff_flow(config, sample_users):
    """SC(FC) → PO(FC) → call-off SC → PO → GR complete chain."""
    admin = sample_users["admin"]
    requester = sample_users["requester"]

    # 1. Create SC(FC)
    sc_fc = create_sc(config, admin, {
        "requester_id": requester["user_id"],
        "request_type": "FC",
        "cost_center": 1000,
        "sc_amount": 100000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
    })
    assert sc_fc["request_type"] == "FC"
    sc_fc = approve_sc(config, admin, sc_fc["sc_id"])

    # 2. Create PO(FC) — requires approved SC(FC) for active status
    po_fc = create_po(config, admin, {
        "sc_id": sc_fc["sc_id"],
        "vendor_id": "V-001",
        "po_amount": 80000,
    })
    assert po_fc["status"] == "active"

    # 3. Create call-off SC under PO(FC)
    calloff_sc = create_sc(config, admin, {
        "requester_id": requester["user_id"],
        "request_type": "material",
        "cost_center": 1000,
        "sc_amount": 50000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-06-30",
        "calloff_po_id": po_fc["po_id"],
    })
    assert calloff_sc["calloff_po_id"] == po_fc["po_id"]
    assert calloff_sc["request_type"] == "material"

    # 4. Submit and approve call-off SC
    calloff_sc = approve_sc(config, admin, calloff_sc["sc_id"])

    # 5. Create regular PO under call-off SC
    regular_po = create_po(config, admin, {
        "sc_id": calloff_sc["sc_id"],
        "vendor_id": "V-001",
        "po_amount": 30000,
    })

    # 6. Create GR under regular PO
    gr = create_gr(config, admin, {
        "po_id": regular_po["po_id"],
        "requester_id": requester["user_id"],
        "estimated_amount": 10000,
    })
    assert gr["po_id"] == regular_po["po_id"]

    # 7. Verify FC PO budget
    fc_budget = compute_po_fc_budget(config, po_fc["po_id"])
    assert fc_budget["allocated_calloff_amount"] == 50000.0
    assert fc_budget["open_po_amount"] == 30000.0


def test_cannot_create_calloff_under_non_fc_po(config, sample_users):
    """Reject call-off SC creation when parent PO is not an FC PO."""
    admin = sample_users["admin"]
    sc = create_sc(config, admin, {
        "requester_id": sample_users["requester"]["user_id"],
        "request_type": "material",
        "cost_center": 1000,
        "sc_amount": 50000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
    })
    sc = approve_sc(config, admin, sc["sc_id"])
    po = create_po(config, admin, {"sc_id": sc["sc_id"], "vendor_id": "V-001", "po_amount": 30000})

    with pytest.raises(ValidationError, match="FC-type SC"):
        create_sc(config, admin, {
            "requester_id": sample_users["requester"]["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 10000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-06-30",
            "calloff_po_id": po["po_id"],
        })


def test_cannot_create_gr_under_fc_po(config, sample_users):
    """Reject GR creation under an FC PO."""
    admin = sample_users["admin"]
    sc_fc = create_sc(config, admin, {
        "requester_id": sample_users["requester"]["user_id"],
        "request_type": "FC",
        "cost_center": 1000,
        "sc_amount": 100000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
    })
    sc_fc = approve_sc(config, admin, sc_fc["sc_id"])
    po_fc = create_po(config, admin, {"sc_id": sc_fc["sc_id"], "vendor_id": "V-001", "po_amount": 80000})

    with pytest.raises(ConflictError, match="FC PO"):
        create_gr(config, admin, {
            "po_id": po_fc["po_id"],
            "requester_id": sample_users["requester"]["user_id"],
            "estimated_amount": 10000,
        })


def test_calloff_sc_amount_exceeds_po_fc_budget(config, sample_users):
    """Reject call-off SC when total would exceed PO(FC) amount."""
    admin = sample_users["admin"]
    sc_fc = create_sc(config, admin, {
        "requester_id": sample_users["requester"]["user_id"],
        "request_type": "FC",
        "cost_center": 1000,
        "sc_amount": 100000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
    })
    sc_fc = approve_sc(config, admin, sc_fc["sc_id"])
    po_fc = create_po(config, admin, {"sc_id": sc_fc["sc_id"], "vendor_id": "V-001", "po_amount": 50000})

    # First call-off uses 40000
    create_sc(config, admin, {
        "requester_id": sample_users["requester"]["user_id"],
        "request_type": "material",
        "cost_center": 1000,
        "sc_amount": 40000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
        "calloff_po_id": po_fc["po_id"],
    })

    # Second call-off of 20000 exceeds remaining 10000
    with pytest.raises(ConflictError, match="exceed"):
        create_sc(config, admin, {
            "requester_id": sample_users["requester"]["user_id"],
            "request_type": "service",
            "cost_center": 1000,
            "sc_amount": 20000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
            "calloff_po_id": po_fc["po_id"],
        })


def test_po_fc_finish_blocked_by_calloff_sc(config, sample_users):
    """PO(FC) cannot finish while call-off SCs are not in final state."""
    admin = sample_users["admin"]
    sc_fc = create_sc(config, admin, {
        "requester_id": sample_users["requester"]["user_id"],
        "request_type": "FC",
        "cost_center": 1000,
        "sc_amount": 100000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
    })
    sc_fc = approve_sc(config, admin, sc_fc["sc_id"])
    po_fc = create_po(config, admin, {"sc_id": sc_fc["sc_id"], "vendor_id": "V-001", "po_amount": 80000})
    create_sc(config, admin, {
        "requester_id": sample_users["requester"]["user_id"],
        "request_type": "material",
        "cost_center": 1000,
        "sc_amount": 30000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
        "calloff_po_id": po_fc["po_id"],
    })

    with pytest.raises(ConflictError, match="call-off"):
        finish_po(config, admin, po_fc["po_id"])
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/test_fc_calloff_flow.py -v`
Expected: all tests pass.

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: all existing tests pass, no regressions.

- [ ] **Step 4: Commit**

```bash
git add tests/test_fc_calloff_flow.py
git commit -m "test: add integration tests for FC call-off flow"
```
