# Independent FC PO Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow creating PO(FC) directly without a parent SC(FC), making `sc_id` nullable and adding `request_type` to the `pos` table.

**Architecture:** Migration v34 rebuilds `pos` with nullable `sc_id` + `request_type TEXT CHECK (IN ('FC'))`, preserving the `finished_by` column from v33. All backend services branch on `sc_id IS NULL` vs `sc_id IS NOT NULL`: lock key switches from `sc:{sc_id}` to `po:{po_id}`, SC validations are skipped, permission checks use PO owner directly. New `get_po_detail` and `get_po` API endpoints serve independent FC PO data. Frontend PoDetailView operates in dual mode detected from route params.

**Tech Stack:** Python (SQLite via sqlite3), Vue 3 + Element Plus + Vue Router

---

### Task 1: Database Migration v34

**Files:**
- Modify: `sc_gr_app/db/migrations.py` (SCHEMA_VERSION, add _migrate_v34, add migrate dispatch)

**Context:** `_migrate_v33` already exists at line 1352 (adds `finished_by` column). Our migration must be v34 and must preserve all existing columns including `finished_by`.

- [ ] **Step 1: Update SCHEMA_VERSION and add _migrate_v34 function**

Change line 9 from `SCHEMA_VERSION = 33` to `SCHEMA_VERSION = 34`.

After `_migrate_v33` (after line 1358), add:

```python
def _migrate_v34(conn) -> None:
    """Make sc_id nullable, add request_type to pos. Rebuild pos + gr_requests."""
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        # Rebuild pos with nullable sc_id and new request_type column
        conn.execute("ALTER TABLE pos RENAME TO pos_old")
        conn.execute("""
            CREATE TABLE pos (
              po_id TEXT PRIMARY KEY,
              sc_id TEXT REFERENCES sc_records(sc_id),
              vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
              po_no TEXT,
              requester_id TEXT,
              po_amount REAL NOT NULL CHECK (po_amount > 0),
              status TEXT NOT NULL CHECK (status IN ('draft','active','finished')),
              request_type TEXT CHECK (request_type IN ('FC')),
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
              finished_by TEXT REFERENCES users(user_id),
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO pos (
              po_id, sc_id, vendor_id, po_no, requester_id, po_amount, status,
              request_type,
              contract_from, contract_to, contract_no, payment_frequency,
              contract_pos, contract_type, cost_center, purchaser,
              active_date, finished_at, finished_by, created_at, updated_at
            )
            SELECT
              po_id, sc_id, vendor_id, po_no, requester_id, po_amount, status,
              NULL,
              contract_from, contract_to, contract_no, payment_frequency,
              contract_pos, contract_type, cost_center, purchaser,
              active_date, finished_at, finished_by, created_at, updated_at
            FROM pos_old
        """)
        conn.execute("DROP TABLE pos_old")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_sc ON pos(sc_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_vendor ON pos(vendor_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_status ON pos(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_requester ON pos(requester_id)")

        # Rebuild gr_requests to fix FK references after pos table rebuild
        if _table_exists(conn, "gr_requests"):
            conn.execute("ALTER TABLE gr_requests RENAME TO gr_requests_old")
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
                  created_by TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT,
                  approved_by TEXT,
                  approved_at TEXT,
                  denied_by TEXT,
                  denied_at TEXT,
                  submitted_date TEXT,
                  pending_date TEXT,
                  approved_date TEXT,
                  goods_service_description TEXT,
                  confirmation_name TEXT,
                  delivery_from TEXT,
                  delivery_to TEXT,
                  last_delivery TEXT
                )
            """)
            conn.execute("INSERT INTO gr_requests SELECT * FROM gr_requests_old")
            conn.execute("DROP TABLE gr_requests_old")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_po ON gr_requests(po_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_status ON gr_requests(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_requester ON gr_requests(requester_id)")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    _record(conn, 34)
```

- [ ] **Step 2: Add migration dispatch in `migrate()`**

After the v33 dispatch block (after line 1540), add:

```python
            if 34 not in _applied_versions(conn):
                conn.execute("PRAGMA foreign_keys = OFF")
                conn.execute("BEGIN")
                _migrate_v34(conn)
                conn.commit()
                conn.execute("PRAGMA foreign_keys = ON")
```

- [ ] **Step 3: Run migration and verify schema**

Run: `python -c "from sc_gr_app.config import AppConfig; from sc_gr_app.db.migrations import migrate; config = AppConfig(); migrate(config)"`

Verify with sqlite3:
```sql
PRAGMA table_info(pos);
-- Should show: sc_id (nullable), request_type (nullable, CHECK), finished_by preserved
SELECT po_id, sc_id, request_type, finished_by FROM pos LIMIT 3;
-- All existing POs: sc_id NOT NULL, request_type NULL, finished_by may have values
```

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/db/migrations.py
git commit -m "feat: add migration v34 — make pos.sc_id nullable, add request_type column"
```

---

### Task 2: po_service.py — All Operations with Branching Logic

**Files:**
- Modify: `sc_gr_app/services/po_service.py`
- Note: `finish_po` starts at line 509. `_finish_po_in_transaction` is at line 465. Both need fixes.

- [ ] **Step 1: Change REQUIRED_FIELDS**

At line 15, change:
```python
REQUIRED_FIELDS = ("sc_id", "vendor_id", "po_amount")
```
to:
```python
REQUIRED_FIELDS = ("vendor_id", "po_amount")
```

- [ ] **Step 2: Rewrite `create_po` with FC PO branching**

Replace the `create_po` function (lines 108-234). Key changes: sc_id conditional, lock key branching, no double `_generate_po_id` call:

```python
def create_po(config: AppConfig, current_user: dict, data: dict) -> dict:
    require_requester_or_admin(current_user)
    _require_fields(data, REQUIRED_FIELDS)
    po_amount = _positive_number(data["po_amount"], "po_amount")

    sc_id = data.get("sc_id")
    request_type = data.get("request_type")
    timestamp = utc_now()

    # Semantic validation
    if sc_id:
        if request_type == "FC":
            raise ValidationError(
                "When sc_id is provided, request_type is derived from SC. Do not set request_type."
            )
    else:
        if request_type != "FC":
            raise ValidationError("When sc_id is empty, request_type must be 'FC'.")

    if sc_id:
        with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
            po_id = _generate_po_id(config, current_user["machine_id"])
            with connect(config) as conn:
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    sc = conn.execute(
                        "select * from sc_records where sc_id = ?", (sc_id,)
                    ).fetchone()
                    if sc is None:
                        raise NotFound(f"SC not found: {sc_id}")

                    sc_status = sc["status"]
                    if sc_status not in ("draft", "approved"):
                        raise ConflictError("SC must be draft or approved")

                    status = data.get("status")
                    if status is None:
                        status = "draft" if sc_status == "draft" else "active"
                    elif status not in SUPPORTED_STATUSES:
                        raise ValidationError("status is invalid")
                    if sc_status == "draft" and status != "draft":
                        raise ConflictError("Draft SC only allows draft PO")
                    if sc_status == "approved" and status == "draft":
                        raise ConflictError("Approved SC does not allow draft PO")

                    if current_user["role"] != "admin" and sc["requester_id"] != current_user["user_id"]:
                        raise PermissionDenied("Only the SC owner or admin can create POs")

                    # Vendor existence + SC-vendor link check
                    vendor = conn.execute(
                        "select vendor_id from vendors where vendor_id = ?",
                        (data["vendor_id"],),
                    ).fetchone()
                    if vendor is None:
                        raise NotFound(f"Vendor not found: {data['vendor_id']}")
                    sc_vendor = conn.execute(
                        "select 1 from sc_vendors where sc_id = ? and vendor_id = ?",
                        (sc_id, data["vendor_id"]),
                    ).fetchone()
                    if sc_vendor is None:
                        raise ValidationError(
                            f"Vendor {data['vendor_id']} is not linked to SC {sc_id}"
                        )

                    is_draft = status == "draft"
                    if not is_draft:
                        budget = compute_sc_budget_decimal(config, sc_id)
                        if budget["allocated_po_amount"] + po_amount > Decimal(str(sc["sc_amount"])):
                            raise ConflictError("PO total would exceed SC amount")

                    active_date_value = None if is_draft else timestamp

                    conn.execute(
                        """insert into pos (
                          po_id, sc_id, vendor_id, po_no, requester_id, po_amount,
                          status, request_type,
                          contract_from, contract_to, contract_no,
                          payment_frequency, contract_pos, contract_type,
                          cost_center, purchaser, active_date,
                          created_at, updated_at
                        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            po_id, sc_id, data["vendor_id"], data.get("po_no"),
                            sc["requester_id"], float(po_amount), status, None,
                            data.get("contract_from"), data.get("contract_to"),
                            data.get("contract_no"), data.get("payment_frequency"),
                            data.get("contract_pos"), data.get("contract_type"),
                            data.get("cost_center") or (str(sc["cost_center"]) if sc["cost_center"] is not None else None),
                            data.get("purchaser"), active_date_value,
                            timestamp, timestamp,
                        ),
                    )
                    created = _get_po(conn, po_id)
                    write_operation_record(
                        conn, action_type="create_po", object_type="po",
                        object_id=po_id, sc_id=sc_id,
                        operator_id=current_user["user_id"],
                        machine_id=current_user["machine_id"],
                        before=None, after=created,
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
    else:
        # Independent FC PO: generate po_id first, then use it as lock key
        po_id = _generate_po_id(config, current_user["machine_id"])
        with LeaseLock(config.lock_dir, f"po:{po_id}", current_user["machine_id"]):
            with connect(config) as conn:
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    vendor = conn.execute(
                        "select vendor_id from vendors where vendor_id = ?",
                        (data["vendor_id"],),
                    ).fetchone()
                    if vendor is None:
                        raise NotFound(f"Vendor not found: {data['vendor_id']}")

                    status = data.get("status", "draft")
                    if status not in SUPPORTED_STATUSES:
                        raise ValidationError("status is invalid")

                    requester_id = data.get("requester_id") or current_user["user_id"]
                    is_draft = status == "draft"
                    active_date_value = None if is_draft else timestamp

                    conn.execute(
                        """insert into pos (
                          po_id, sc_id, vendor_id, po_no, requester_id, po_amount,
                          status, request_type,
                          contract_from, contract_to, contract_no,
                          payment_frequency, contract_pos, contract_type,
                          cost_center, purchaser, active_date,
                          created_at, updated_at
                        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            po_id, None, data["vendor_id"], data.get("po_no"),
                            requester_id, float(po_amount), status, "FC",
                            data.get("contract_from"), data.get("contract_to"),
                            data.get("contract_no"), data.get("payment_frequency"),
                            data.get("contract_pos"), data.get("contract_type"),
                            data.get("cost_center"), data.get("purchaser"),
                            active_date_value, timestamp, timestamp,
                        ),
                    )
                    created = _get_po(conn, po_id)
                    write_operation_record(
                        conn, action_type="create_po", object_type="po",
                        object_id=po_id, sc_id=None,
                        operator_id=current_user["user_id"],
                        machine_id=current_user["machine_id"],
                        before=None, after=created,
                    )
                    notification_service.queue_status_change(
                        conn, "po", po_id, "create",
                        {"requester_id": requester_id}, current_user
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

    return created
```

- [ ] **Step 3: Rewrite `submit_po` with lock key branching**

Replace the `submit_po` function body (lines 283-324) with:

```python
def submit_po(config: AppConfig, current_user: dict, po_id: str) -> dict:
    """Manually submit a draft PO to active status (with budget check)."""
    require_requester_or_admin(current_user)

    with connect(config) as lookup_conn:
        po = _get_po_or_raise(lookup_conn, po_id)
        sc_id = po["sc_id"]
    lock_key = f"sc:{sc_id}" if sc_id else f"po:{po_id}"

    with LeaseLock(config.lock_dir, lock_key, current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)
                if before["status"] != "draft":
                    raise ConflictError("PO must be draft to submit")

                if sc_id:
                    sc = conn.execute(
                        "SELECT status, sc_amount FROM sc_records WHERE sc_id = ?", (sc_id,)
                    ).fetchone()
                    if sc is None:
                        raise ConflictError("SC not found")
                    if sc["status"] == "draft":
                        raise ConflictError(
                            "Cannot submit PO while SC is still draft. Submit the SC first."
                        )
                    if sc["sc_amount"] is not None:
                        po_amount = Decimal(str(before["po_amount"]))
                        budget = compute_sc_budget_decimal(config, sc_id)
                        if budget["allocated_po_amount"] + po_amount > Decimal(str(sc["sc_amount"])):
                            raise ConflictError("PO total would exceed SC amount")

                timestamp = utc_now()
                _submit_po_drafts(conn, [po_id], timestamp)
                after = _get_po_or_raise(conn, po_id)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after
```

**Note:** `_submit_po_drafts` crashes for independent FC PO because it reads `sc["requester_id"]` from a null-sc lookup. Step 8 fixes this. Until Step 8 is applied, independent FC PO submission will fail. Apply Steps 1-3 + 8 before testing independent FC PO flow.

- [ ] **Step 4: Rewrite `update_po` with lock/sc/vendor branching**

Replace the `update_po` function (lines 327-462). Key changes: lock key branches on sc_id; permission check uses PO owner directly when sc_id is null; SC validations and vendor-SC link check are skipped for independent FC PO.

```python
def update_po(config: AppConfig, current_user: dict, po_id: str, data: dict) -> dict:
    require_requester_or_admin(current_user)
    allowed_fields = {
        "vendor_id", "po_no", "po_amount", "contract_from", "contract_to",
        "contract_no", "payment_frequency", "contract_pos", "contract_type",
        "cost_center", "purchaser", "active_date",
    }
    updates = {key: value for key, value in data.items() if key in allowed_fields}
    if not updates:
        raise ValidationError("No PO fields to update")

    with connect(config) as lookup_conn:
        before_lookup = _get_po_or_raise(lookup_conn, po_id)
        sc_id = before_lookup["sc_id"]
    lock_key = f"sc:{sc_id}" if sc_id else f"po:{po_id}"

    with LeaseLock(config.lock_dir, lock_key, current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)

                if sc_id:
                    sc = conn.execute(
                        "select * from sc_records where sc_id = ?", (before["sc_id"],)
                    ).fetchone()
                    if sc["status"] == "finished":
                        raise ConflictError("Finished SC cannot be edited")
                    if before["status"] == "draft" and sc["status"] == "finished":
                        raise ConflictError("Finished SC cannot be edited")
                    if current_user["role"] != "admin" and sc["requester_id"] != current_user["user_id"]:
                        raise PermissionDenied("Only the SC owner or admin can edit POs")
                else:
                    if current_user["role"] != "admin" and before["requester_id"] != current_user["user_id"]:
                        raise PermissionDenied("Only the PO owner or admin can edit this PO")

                if before["status"] == "finished":
                    raise ConflictError("Finished PO cannot be edited")

                merged = {**before, **updates}
                po_amount = _positive_number(merged["po_amount"], "po_amount")
                if po_amount < _po_gr_usage(conn, po_id):
                    raise ConflictError("PO amount cannot be below GR usage")

                if merged["vendor_id"] != before["vendor_id"]:
                    vendor = conn.execute(
                        "select vendor_id from vendors where vendor_id = ?",
                        (merged["vendor_id"],),
                    ).fetchone()
                    if vendor is None:
                        raise NotFound(f"Vendor not found: {merged['vendor_id']}")
                    if sc_id:
                        sc_vendor = conn.execute(
                            "select 1 from sc_vendors where sc_id = ? and vendor_id = ?",
                            (sc_id, merged["vendor_id"]),
                        ).fetchone()
                        if sc_vendor is None:
                            raise ValidationError(
                                f"Vendor {merged['vendor_id']} is not linked to SC {sc_id}"
                            )

                if sc_id:
                    sibling_total = sum(
                        (Decimal(str(row["po_amount"]))
                         for row in conn.execute(
                            "select po_amount from pos where sc_id = ? and po_id != ?",
                            (before["sc_id"], po_id),
                        )),
                        Decimal("0"),
                    )
                    sc = conn.execute(
                        "select sc_amount, request_type from sc_records where sc_id = ?",
                        (before["sc_id"],),
                    ).fetchone()
                    if sibling_total + po_amount > Decimal(str(sc["sc_amount"])):
                        raise ConflictError("PO total would exceed SC amount")

                # FC PO call-off amount check
                is_fc = before.get("request_type") == "FC"
                if not is_fc and sc_id:
                    parent_sc = conn.execute(
                        "select request_type from sc_records where sc_id = ?",
                        (before["sc_id"],),
                    ).fetchone()
                    is_fc = parent_sc and parent_sc["request_type"] == "FC"

                if is_fc and "po_amount" in updates:
                    calloff_total = conn.execute(
                        "select coalesce(sum(sc_amount), 0) from sc_records "
                        "where calloff_po_id = ?",
                        (po_id,),
                    ).fetchone()[0]
                    if po_amount < Decimal(str(calloff_total)):
                        raise ConflictError(
                            "PO amount cannot be below allocated call-off SC amounts"
                        )

                timestamp = utc_now()
                conn.execute(
                    """update pos
                       set vendor_id = ?, po_no = ?, po_amount = ?,
                           contract_from = ?, contract_to = ?, contract_no = ?,
                           payment_frequency = ?, contract_pos = ?, contract_type = ?,
                           cost_center = ?, purchaser = ?, active_date = ?,
                           updated_at = ?
                       where po_id = ?""",
                    (
                        merged["vendor_id"], merged.get("po_no"), float(po_amount),
                        merged.get("contract_from"), merged.get("contract_to"),
                        merged.get("contract_no"), merged.get("payment_frequency"),
                        merged.get("contract_pos"), merged.get("contract_type"),
                        merged.get("cost_center"), merged.get("purchaser"),
                        merged.get("active_date"), timestamp, po_id,
                    ),
                )
                after = _get_po_or_raise(conn, po_id)
                write_operation_record(
                    conn, action_type="update_po", object_type="po",
                    object_id=po_id, sc_id=before["sc_id"],
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before, after=after,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after
```

- [ ] **Step 5: Fix `_finish_po_in_transaction` for null sc_id AND rewrite `finish_po` for lock key branching**

`_finish_po_in_transaction` (lines 465-506) is called from `finish_po` AND from `sc_service.py` for cascade finishes. It queries `sc_records where sc_id = ?` with `before["sc_id"]`. For independent FC PO, `sc_id` is NULL, returning no row, and the notification code accesses `sc["requester_id"]` on None → crash.

Fix `_finish_po_in_transaction` (lines 465-506):

```python
def _finish_po_in_transaction(conn, po_id: str, current_user: dict, timestamp: str) -> dict:
    """Finish a PO within an existing transaction. Must NOT acquire locks."""
    before = _get_po_or_raise(conn, po_id)

    sc = None
    if before.get("sc_id"):
        sc = conn.execute(
            "select status, requester_id from sc_records where sc_id = ?",
            (before["sc_id"],),
        ).fetchone()
    if sc and sc["status"] == "finished":
        raise ConflictError("Finished SC cannot be edited")
    if before["status"] != "active":
        raise ConflictError("PO must be active")

    conn.execute(
        """update pos set status = 'finished', updated_at = ?, finished_at = ?,
           finished_by = ? where po_id = ?""",
        (timestamp, timestamp, current_user["user_id"], po_id),
    )
    after = _get_po_or_raise(conn, po_id)

    write_operation_record(
        conn, action_type="finish_po", object_type="po",
        object_id=po_id, sc_id=before["sc_id"],
        operator_id=current_user["user_id"],
        machine_id=current_user["machine_id"],
        before=before, after=after,
    )
    notification_service.queue_status_change(
        conn, "po", po_id, "finish",
        {"requester_id": sc["requester_id"]} if sc
        else {"requester_id": before.get("requester_id", "")},
        current_user
    )
    return after
```

Then rewrite `finish_po` (lines 509-560) with lock key branching:

```python
def finish_po(config: AppConfig, current_user: dict, po_id: str) -> dict:
    require_requester_or_admin(current_user)

    with connect(config) as lookup_conn:
        before = _get_po_or_raise(lookup_conn, po_id)
        sc_id = before["sc_id"]
    lock_key = f"sc:{sc_id}" if sc_id else f"po:{po_id}"

    with LeaseLock(config.lock_dir, lock_key, current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before_tx = _get_po_or_raise(conn, po_id)
                if before_tx["status"] != "active":
                    raise ConflictError("PO must be active")

                # Call-off SC final state check for FC POs
                is_fc = before_tx.get("request_type") == "FC"
                if not is_fc and before_tx.get("sc_id"):
                    parent_sc = conn.execute(
                        "select request_type from sc_records where sc_id = ?",
                        (before_tx["sc_id"],),
                    ).fetchone()
                    is_fc = parent_sc and parent_sc["request_type"] == "FC"

                if is_fc:
                    non_final_calloffs = conn.execute(
                        """SELECT sc_id, status FROM sc_records
                           WHERE calloff_po_id = ? AND status NOT IN ('finished', 'denied')""",
                        (po_id,),
                    ).fetchall()
                    if non_final_calloffs:
                        raise ConflictError(
                            f"Cannot finish PO: {len(non_final_calloffs)} call-off SC(s) "
                            "not in final state. Finish or deny all call-off SCs first."
                        )
                else:
                    non_final_grs = conn.execute(
                        """SELECT gr_id, status FROM gr_requests
                           WHERE po_id = ? AND status NOT IN ('denied', 'finished')""",
                        (po_id,),
                    ).fetchall()
                    if non_final_grs:
                        raise ConflictError(
                            f"Cannot finish PO: {len(non_final_grs)} GR(s) not in final state. "
                            "Approve, deny or finish all GRs first."
                        )

                timestamp = utc_now()
                after = _finish_po_in_transaction(conn, po_id, current_user, timestamp)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after
```

- [ ] **Step 6: Rewrite `recall_po` with lock/owner branching**

Replace `recall_po` (lines 603-680) with:

```python
def recall_po(config: AppConfig, current_user: dict, po_id: str) -> dict:
    """Recall PO back to draft."""

    with connect(config) as lookup_conn:
        po = _get_po_or_raise(lookup_conn, po_id)
        sc_id = po["sc_id"]

        if sc_id:
            sc = lookup_conn.execute(
                "select status, requester_id from sc_records where sc_id = ?", (sc_id,)
            ).fetchone()
            if sc is None:
                raise NotFound(f"SC {sc_id} not found")
            if sc["requester_id"] != current_user["user_id"]:
                raise PermissionDenied("Only the SC requester can recall POs")
            if sc["status"] == "finished":
                raise ConflictError("Finished SC cannot be edited")
        else:
            if po["requester_id"] != current_user["user_id"] and current_user.get("role") != "admin":
                raise PermissionDenied("Only the PO owner or admin can recall")

    lock_key = f"sc:{sc_id}" if sc_id else f"po:{po_id}"

    with LeaseLock(config.lock_dir, lock_key, current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)
                if before["status"] != "active":
                    raise ConflictError("Only active PO can be recalled back to draft")

                is_fc = before.get("request_type") == "FC"
                if not is_fc and sc_id:
                    parent_sc = conn.execute(
                        "select request_type from sc_records where sc_id = ?",
                        (before["sc_id"],),
                    ).fetchone()
                    is_fc = parent_sc and parent_sc["request_type"] == "FC"

                if is_fc:
                    non_draft_calloffs = conn.execute(
                        "select count(*) from sc_records where calloff_po_id = ? and status != 'draft'",
                        (po_id,),
                    ).fetchone()[0]
                    if non_draft_calloffs > 0:
                        raise ConflictError("Cannot recall PO(FC): non-draft call-off SCs exist")
                else:
                    non_draft_gr_count = conn.execute(
                        "select count(*) from gr_requests where po_id = ? and status != 'draft'",
                        (po_id,),
                    ).fetchone()[0]
                    if non_draft_gr_count > 0:
                        raise ConflictError("Cannot recall PO with existing non-draft GRs")

                timestamp = utc_now()
                conn.execute(
                    "update pos set status = 'draft', updated_at = ? where po_id = ?",
                    (timestamp, po_id),
                )
                after = _get_po_or_raise(conn, po_id)
                write_operation_record(
                    conn, action_type="recall_po", object_type="po",
                    object_id=po_id, sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before, after=after,
                )
                if sc_id:
                    sc_requester = conn.execute(
                        "SELECT requester_id FROM sc_records WHERE sc_id = ?",
                        (before["sc_id"],),
                    ).fetchone()
                    notification_service.queue_status_change(
                        conn, "po", po_id, "recall",
                        {"requester_id": sc_requester["requester_id"]} if sc_requester else {},
                        current_user
                    )
                else:
                    notification_service.queue_status_change(
                        conn, "po", po_id, "recall",
                        {"requester_id": before["requester_id"]}, current_user
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after
```

- [ ] **Step 7: Rewrite `delete_po` with lock/owner branching**

Replace `delete_po` (line 683 onward) with:

```python
def delete_po(config: AppConfig, current_user: dict, po_id: str) -> dict:
    """Delete a draft PO and its GRs/attachments. Admin or PO owner."""
    require_requester_or_admin(current_user)

    with connect(config) as lookup_conn:
        po = _get_po_or_raise(lookup_conn, po_id)
        sc_id = po["sc_id"]
    lock_key = f"sc:{sc_id}" if sc_id else f"po:{po_id}"

    with LeaseLock(config.lock_dir, lock_key, current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)
                if before["status"] != "draft":
                    raise ConflictError("Only draft PO can be deleted")

                is_fc = before.get("request_type") == "FC"
                if not is_fc and sc_id:
                    parent_sc = conn.execute(
                        "select request_type from sc_records where sc_id = ?",
                        (before["sc_id"],),
                    ).fetchone()
                    is_fc = parent_sc and parent_sc["request_type"] == "FC"

                if is_fc:
                    calloff_exists = conn.execute(
                        "select 1 from sc_records where calloff_po_id = ? limit 1", (po_id,)
                    ).fetchone()
                    if calloff_exists:
                        raise ConflictError("Cannot delete PO(FC) with existing call-off SCs")

                # Permission check
                if sc_id:
                    sc = conn.execute(
                        "SELECT requester_id FROM sc_records WHERE sc_id = ?",
                        (before["sc_id"],),
                    ).fetchone()
                    if current_user["role"] != "admin" and (
                        sc is None or sc["requester_id"] != current_user["user_id"]
                    ):
                        raise PermissionDenied("Only the SC owner or admin can delete")
                else:
                    if current_user["role"] != "admin" and before["requester_id"] != current_user["user_id"]:
                        raise PermissionDenied("Only the PO owner or admin can delete")

                attach_paths = [
                    row["stored_path"] for row in conn.execute(
                        "SELECT stored_path FROM attachments WHERE entity_type = 'po' "
                        "AND entity_id = ?", (po_id,)
                    ).fetchall()
                ]
                attach_paths.extend(
                    row["stored_path"] for row in conn.execute(
                        "SELECT stored_path FROM attachments WHERE entity_type = 'gr' "
                        "AND entity_id IN (SELECT gr_id FROM gr_requests WHERE po_id = ?)",
                        (po_id,),
                    ).fetchall()
                )

                conn.execute("DELETE FROM attachments WHERE entity_type = 'gr' AND entity_id IN ("
                             "SELECT gr_id FROM gr_requests WHERE po_id = ?)", (po_id,))
                conn.execute("DELETE FROM gr_requests WHERE po_id = ?", (po_id,))
                conn.execute("DELETE FROM attachments WHERE entity_type = 'po' AND entity_id = ?", (po_id,))
                conn.execute("DELETE FROM pos WHERE po_id = ?", (po_id,))

                write_operation_record(
                    conn, action_type="delete_po", object_type="po",
                    object_id=po_id, sc_id=before["sc_id"],
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before, after=None,
                )
                conn.commit()

                for path in attach_paths:
                    try:
                        Path(path).unlink(missing_ok=True)
                    except OSError:
                        pass
            except Exception:
                conn.rollback()
                raise

    return before
```

- [ ] **Step 8: Fix `_submit_po_drafts` notification for null sc_id**

In `_submit_po_drafts` (lines 237-280), change lines 270-278 from:

```python
        sc = conn.execute(
            "SELECT requester_id FROM sc_records WHERE sc_id = ?",
            (after["sc_id"],),
        ).fetchone()
        notification_service.queue_status_change(
            conn, "po", po_id, "submit",
            {"requester_id": sc["requester_id"]} if sc else {},
            {"user_id": after.get("created_by", "SYSTEM"), "machine_id": "SYSTEM_CASCADE"}
        )
```

to:

```python
        if after.get("sc_id"):
            sc = conn.execute(
                "SELECT requester_id FROM sc_records WHERE sc_id = ?",
                (after["sc_id"],),
            ).fetchone()
            notification_service.queue_status_change(
                conn, "po", po_id, "submit",
                {"requester_id": sc["requester_id"]} if sc else {},
                {"user_id": after.get("created_by", "SYSTEM"), "machine_id": "SYSTEM_CASCADE"}
            )
        else:
            notification_service.queue_status_change(
                conn, "po", po_id, "submit",
                {"requester_id": after.get("requester_id", "")},
                {"user_id": after.get("created_by", "SYSTEM"), "machine_id": "SYSTEM_CASCADE"}
            )
```

- [ ] **Step 9: Commit**

```bash
git add sc_gr_app/services/po_service.py
git commit -m "feat: support independent FC PO in all PO operations (create/submit/update/finish/recall/delete)"
```

---

### Task 3: sc_service.py — _validate_calloff_po LEFT JOIN Fix

**Files:**
- Modify: `sc_gr_app/services/sc_service.py`

- [ ] **Step 1: Fix `_validate_calloff_po` query (lines 78-90)**

The query at line 81 uses INNER JOIN `pos po join sc_records sc on sc.sc_id = po.sc_id`. For independent FC PO (`sc_id IS NULL`), returns no row → `NotFound("PO not found")`.

Change to LEFT JOIN + check both `pos.request_type` and `sc.request_type`:

```python
    po_row = conn.execute(
        """select po.po_id, po.po_amount, po.status,
                  po.request_type as po_request_type,
                  sc.request_type as parent_sc_type
           from pos po
           left join sc_records sc on sc.sc_id = po.sc_id
           where po.po_id = ?""",
        (calloff_po_id,),
    ).fetchone()
    if po_row is None:
        raise NotFound(f"PO not found: {calloff_po_id}")
    is_fc_po = (po_row["po_request_type"] == "FC" or po_row["parent_sc_type"] == "FC")
    if not is_fc_po:
        raise ValidationError(
            "Call-off PO must be an FC-type PO (either independent or under SC(FC))"
        )
    if po_row["status"] != "active":
        raise ConflictError("Call-off PO must be active to create call-off SCs")
```

- [ ] **Step 2: Fix `get_sc_detail` parent PO info INNER JOIN → LEFT JOIN**

In `get_sc_detail`, the parent PO query for call-off SCs (around line 1249) uses:
```sql
from pos po join sc_records sc_parent on sc_parent.sc_id = po.sc_id
```
For call-off SCs under independent FC PO, this returns NULL → parent PO info not shown.

Change to:
```sql
from pos po left join sc_records sc_parent on sc_parent.sc_id = po.sc_id
```

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/services/sc_service.py
git commit -m "fix: LEFT JOIN for call-off PO validation to support independent FC PO"
```

---

### Task 4: budget_service.py — compute_po_fc_budget Null sc_id Fix

**Files:**
- Modify: `sc_gr_app/services/budget_service.py`

- [ ] **Step 1: Fix `compute_po_fc_budget_decimal` for null sc_id**

At lines 96-108, the function fetches the parent SC with `sc_records where sc_id = ?` and raises `NotFound(f"PO references non-existent SC: {po['sc_id']}")` when sc_id is NULL.

Change to:

```python
        po = conn.execute(
            "select po_amount, sc_id, request_type from pos where po_id = ?",
            (po_id,),
        ).fetchone()
        if po is None:
            raise NotFound(f"PO not found: {po_id}")

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

**Note:** `compute_po_fc_budget` (float wrapper at ~line 174) delegates to `compute_po_fc_budget_decimal`. Only the decimal version needs this fix.

- [ ] **Step 2: Commit**

```bash
git add sc_gr_app/services/budget_service.py
git commit -m "fix: handle null sc_id in compute_po_fc_budget for independent FC PO"
```

---

### Task 5: query_service.py — search_pos, workbench_data, Visibility

**Files:**
- Modify: `sc_gr_app/services/query_service.py`

- [ ] **Step 1: Fix `search_pos` — INNER JOIN → LEFT JOIN**

At the main FROM/JOIN for `sc_records` in `search_pos`, change:
```sql
        join sc_records sc on sc.sc_id = po.sc_id
```
to:
```sql
        left join sc_records sc on sc.sc_id = po.sc_id
```

- [ ] **Step 2: Fix `search_pos` — add COALESCE for sc_request_type in SELECT**

Change:
```sql
          sc.request_type as sc_request_type,
```
to:
```sql
          coalesce(pos.request_type, sc.request_type) as sc_request_type,
```

- [ ] **Step 3: Fix `search_pos` — open_po_amount CASE**

Change:
```sql
          case when sc.request_type = 'FC'
            then po.po_amount - coalesce(calloff_totals.allocated, 0)
            else po.po_amount - coalesce(gr_totals.pending_total, 0)
                 - coalesce(gr_totals.con_value_total, 0)
          end as open_po_amount,
```
to:
```sql
          case when pos.request_type = 'FC' or sc.request_type = 'FC'
            then po.po_amount - coalesce(calloff_totals.allocated, 0)
            else po.po_amount - coalesce(gr_totals.pending_total, 0)
                 - coalesce(gr_totals.con_value_total, 0)
          end as open_po_amount,
```

- [ ] **Step 4: Fix `search_pos` — is_fc_po filter**

Change:
```python
    if filters and "is_fc_po" in filters:
        if filters["is_fc_po"] == "1":
            base_clauses.append("sc.request_type = 'FC'")
        elif filters["is_fc_po"] == "0":
            base_clauses.append("sc.request_type != 'FC'")
```
to:
```python
    if filters and "is_fc_po" in filters:
        if filters["is_fc_po"] == "1":
            base_clauses.append("(pos.request_type = 'FC' OR sc.request_type = 'FC')")
        elif filters["is_fc_po"] == "0":
            base_clauses.append("(pos.request_type IS NULL AND sc.request_type != 'FC')")
```

- [ ] **Step 5: Fix `search_pos` — independent FC PO visibility fallback for non-admin users**

`_sc_visibility_clauses` returns clauses like `sc.status != 'draft'` and `sc.requester_id = ?`. After LEFT JOIN, `sc.status` is NULL for independent FC PO, so `sc.status != 'draft'` evaluates to NULL (not TRUE), silently excluding them.

After the `_sc_visibility_clauses` call (around where base_clauses/base_params are assembled), add a fallback that wraps each clause with an OR for `po.sc_id IS NULL`:

For a requester, `_sc_visibility_clauses` returns:
- clauses: `["sc.status != 'draft'", "sc.requester_id = ?"]`
- params: `[current_user["user_id"]]` (1 param for the `?` in clause 1)

After wrapping, each clause gains `OR (po.sc_id IS NULL AND po.requester_id = ?)`:
- `(sc.status != 'draft' OR (po.sc_id IS NULL AND po.requester_id = ?))` — 1 placeholder
- `(sc.requester_id = ? OR (po.sc_id IS NULL AND po.requester_id = ?))` — 2 placeholders

Total: 3 `?` placeholders, so params must be `[user_id, user_id, user_id]` (3 params).

```python
    base_clauses, base_params = _sc_visibility_clauses(current_user)

    if current_user and current_user.get("role") == "requester":
        base_clauses = [
            f"({c} OR (po.sc_id IS NULL AND po.requester_id = ?))"
            for c in base_clauses
        ]
        # Count total ? placeholders across all wrapped clauses
        total_placeholders = sum(c.count("?") for c in base_clauses)
        base_params = [current_user["user_id"]] * total_placeholders
```

**Note:** For admin users, `_sc_visibility_clauses` returns empty clauses — admins see all POs. No fallback needed.

- [ ] **Step 6: Fix `search_pos` — add `is_independent` filter**

Add a special filter for querying independent FC POs (sc_id IS NULL / IS NOT NULL). Place it alongside the `is_fc_po` filter block:

```python
    if filters and "is_independent" in filters:
        if filters["is_independent"] == "1":
            base_clauses.append("po.sc_id IS NULL")
        elif filters["is_independent"] == "0":
            base_clauses.append("po.sc_id IS NOT NULL")
        filters = {k: v for k, v in filters.items() if k != "is_independent"}
```

- [ ] **Step 7: Fix `workbench_data` — INNER JOIN → LEFT JOIN**

At the detail ROWS query (around the JOIN line), change:
```sql
                f"JOIN sc_records sc ON sc.sc_id = po.sc_id "
```
to:
```sql
                f"LEFT JOIN sc_records sc ON sc.sc_id = po.sc_id "
```

- [ ] **Step 8: Fix `workbench_data` — open_po_amount CASE**

Change:
```sql
                f"CASE WHEN sc.request_type = 'FC' "
                f"THEN po.po_amount - COALESCE(calloff_sums.allocated, 0) "
                f"ELSE po.po_amount - COALESCE(gr_sums.pending_total, 0) "
                f"- COALESCE(gr_sums.con_value_total, 0) END AS open_po_amount "
```
to:
```sql
                f"CASE WHEN pos.request_type = 'FC' OR sc.request_type = 'FC' "
                f"THEN po.po_amount - COALESCE(calloff_sums.allocated, 0) "
                f"ELSE po.po_amount - COALESCE(gr_sums.pending_total, 0) "
                f"- COALESCE(gr_sums.con_value_total, 0) END AS open_po_amount "
```

- [ ] **Step 9: Commit**

```bash
git add sc_gr_app/services/query_service.py
git commit -m "fix: LEFT JOIN and FC type detection in search_pos and workbench_data for independent FC PO"
```

---

### Task 6: gr_service.py — FC Gates on All Operations

**Files:**
- Modify: `sc_gr_app/services/gr_service.py`

- [ ] **Step 1: Fix `create_gr` — two-step PO lookup (lines 214-219)**

Replace the INNER JOIN lookup with a two-step approach that checks `pos.request_type` first:

```python
    with connect(config) as lookup_conn:
        lookup = lookup_conn.execute(
            "select sc_id, request_type, requester_id from pos where po_id = ?",
            (po_id,),
        ).fetchone()
        if lookup is None:
            raise NotFound(f"PO not found: {po_id}")

        is_fc = (lookup["request_type"] == "FC")
        if not is_fc and lookup["sc_id"]:
            sc_info = lookup_conn.execute(
                "select request_type from sc_records where sc_id = ?",
                (lookup["sc_id"],),
            ).fetchone()
            if sc_info and sc_info["request_type"] == "FC":
                is_fc = True

        if is_fc:
            raise ConflictError(
                "Cannot create GR under an FC PO. Create a call-off SC instead."
            )

        sc_id = lookup["sc_id"]
        if sc_id is None:
            raise ConflictError("Cannot create GR under an independent PO")

        if current_user["role"] != "admin":
            sc_requester = lookup_conn.execute(
                "select requester_id from sc_records where sc_id = ?", (sc_id,)
            ).fetchone()
            if sc_requester and sc_requester["requester_id"] != current_user["user_id"]:
                raise PermissionDenied("Only the SC owner or admin can create GRs")
```

- [ ] **Step 2: Add FC gate helper function**

At the top of gr_service.py (near the other helpers), add:

```python
def _check_not_fc_po(conn, po_id: str) -> None:
    """Raise ConflictError if the PO is an FC PO (either independent or SC-derived)."""
    po = conn.execute(
        "select sc_id, request_type from pos where po_id = ?", (po_id,)
    ).fetchone()
    if po is None:
        raise NotFound(f"PO not found: {po_id}")
    is_fc = (po["request_type"] == "FC")
    if not is_fc and po["sc_id"]:
        sc = conn.execute(
            "select request_type from sc_records where sc_id = ?", (po["sc_id"],)
        ).fetchone()
        if sc and sc["request_type"] == "FC":
            is_fc = True
    if is_fc:
        raise ConflictError("Cannot perform GR operations under an FC PO.")
```

- [ ] **Step 3: Add FC gate to all 8 remaining GR operations**

In each of these functions, add `_check_not_fc_po(conn, po_id)` after the initial PO context is available and before any mutation:

- `submit_gr` — after `_get_po_sc` call
- `confirm_gr` — after `_get_po_sc` call
- `approve_gr` — after `_get_po_sc` call
- `deny_gr` — after `_get_po_sc` call
- `finish_gr` — after `_get_po_sc` call
- `recall_gr` — after `_get_po_sc` call
- `update_gr` — after `_get_po_sc` call
- `delete_gr` — after `_get_po_sc` call

Example for `submit_gr`:
```python
    po_sc = _get_po_sc(conn, gr_row["po_id"])
    _check_not_fc_po(conn, gr_row["po_id"])
    # ... rest of submit logic
```

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/services/gr_service.py
git commit -m "fix: add FC PO gates to all GR operations for defense-in-depth"
```

---

### Task 7: export_service.py — Effective FC Type Detection

**Files:**
- Modify: `sc_gr_app/services/export_service.py`

- [ ] **Step 1: Fix `_build_po_cascade` — use effective type**

At the PO cascade building code (around lines 94-110), the FC type detection uses only `sc_request_type` from the SC lookup. For independent FC PO, `sc` is None and `sc_request_type = ""`, so it falls through to the GR branch instead of the call-off SC branch.

Change the type detection:

```python
            sc = None
            if po.get("sc_id"):
                sc = conn.execute(
                    "SELECT sc_no, request_type FROM sc_records WHERE sc_id = ?",
                    (po["sc_id"],),
                ).fetchone()
            po["sc_no"] = sc["sc_no"] if sc else ""
            effective_type = po.get("request_type") or (sc["request_type"] if sc else "")
```

Then change the branch condition from `if sc_request_type == "FC"` to `if effective_type == "FC"`.

Note: `search_pos` selects `po.*` which includes `po.request_type` after migration. `_build_po_cascade` reads `po.get("request_type")` — this is sufficient. No additional SELECT change needed.

- [ ] **Step 2: Commit**

```bash
git add sc_gr_app/services/export_service.py
git commit -m "fix: use effective type for FC PO detection in export cascade"
```

---

### Task 8: import_service.py — Validation, Import, Preview, Template

**Files:**
- Modify: `sc_gr_app/services/import_service.py`
- Modify: `sc_gr_app/api/bridge.py` (template download, lines ~1939-1965)

- [ ] **Step 1: Fix `_validate_po_rows` — required fields and semantic validation**

At the `_validate_po_rows` function, change the validation logic:

1. Make `sc_no` conditionally required (skip when `request_type == 'FC'`);
2. Add semantic validation for the four-cell combinations;
3. Allow `draft` status for FC POs.

```python
    for i, row in enumerate(rows, start=1):
        if _is_template_meta_row(row, "po_no"):
            continue

        # Extract request_type early for conditional validation
        request_type = str(row.get("request_type", "")).strip()
        sc_no = str(row.get("sc_no", "")).strip()

        # Required fields: sc_no is required only for non-FC POs
        required = ["po_no", "po_amount", "status"]
        if request_type != "FC":
            required.append("sc_no")
        for field in required:
            val = row.get(field)
            if val is None or str(val).strip() == "":
                errors.append({"row": i, "field": field, "message": f"{field} is required"})

        # Status validation: draft allowed for FC POs
        status = str(row.get("status", "")).strip()
        allowed = PO_IMPORT_ALLOWED_STATUSES.copy()
        if request_type == "FC":
            allowed.add("draft")
        if status and status not in allowed:
            errors.append({"row": i, "field": "status", "message": f"Invalid status: {status}"})

        # Semantic validation: four-cell combinations
        if sc_no and request_type == "FC":
            errors.append({"row": i, "field": "request_type",
                "message": "When sc_no is provided, do not set request_type (derived from SC)"})
        if not sc_no and request_type != "FC":
            errors.append({"row": i, "field": "request_type",
                "message": "When sc_no is empty, request_type must be 'FC'"})

        # ... existing SC existence / vendor checks follow (unchanged, already conditional on sc_no)
```

- [ ] **Step 2: Fix `preview_po_import` — same validation changes**

`preview_po_import` (starts ~line 480) has its own copy of validation logic. Apply the same changes as Step 1:
- Conditional `sc_no` required field
- Semantic validation for `sc_no` + `request_type` combinations
- Draft allowed for FC POs

- [ ] **Step 3: Fix `import_pos` — request_type in INSERT, handle null sc_no**

In the `import_pos` function:

1. Add `request_type` to the INSERT column list and values.
2. Handle `sc_no` being empty → `sc_id = None`.
3. Use `row.get("sc_no")` instead of `row["sc_no"]` (KeyError risk when empty).

```python
                    sc_no = (row.get("sc_no") or "").strip()
                    sc_id = None
                    if sc_no:
                        sc_row = conn.execute(
                            "SELECT sc_id FROM sc_records WHERE sc_no = ?", (sc_no,)
                        ).fetchone()
                        sc_id = sc_row["sc_id"] if sc_row else None

                    conn.execute(
                        """INSERT INTO pos (
                          po_id, sc_id, vendor_id, po_no, requester_id,
                          po_amount, status, request_type,
                          contract_from, contract_to, contract_no,
                          payment_frequency, contract_pos, contract_type, cost_center,
                          purchaser, active_date, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            po_id, sc_id, row.get("vendor_id"), po_no,
                            row.get("requester_id") or current_user["user_id"],
                            float(row["po_amount"]) if row.get("po_amount") else None,
                            row.get("status", "draft"),
                            row.get("request_type") if row.get("request_type") else None,
                            parse_date(row.get("contract_from")),
                            parse_date(row.get("contract_to")),
                            row.get("contract_no"),
                            row.get("payment_frequency"),
                            row.get("contract_pos"),
                            row.get("contract_type"),
                            row.get("cost_center"),
                            row.get("purchaser"),
                            parse_date(row.get("active_date")) if row.get("active_date") else None,
                            timestamp,
                            timestamp,
                        ),
                    )
```

- [ ] **Step 4: Fix `_validate_sc_rows` — calloff_po_id LEFT JOIN**

At the calloff PO validation (~lines 119-126), change:
```sql
select 1 from pos po join sc_records sc on sc.sc_id = po.sc_id
where po.po_id = ? and sc.request_type = 'FC'
```
to:
```sql
select 1 from pos po left join sc_records sc on sc.sc_id = po.sc_id
where po.po_id = ? and (po.request_type = 'FC' or sc.request_type = 'FC')
```

- [ ] **Step 5: Fix `download_po_template` in bridge.py — keep sc_no, add request_type**

The current template uses `sc_no` (human-readable), not `sc_id` (system ID). The import code reads `sc_no` and resolves it to `sc_id` via DB lookup. Keep the column as `sc_no`.

Update headers (~line 1939):
```python
        headers = ["po_id", "sc_no", "vendor_id", "po_no", "requester_id",
                   "request_type", "po_amount", "status", "contract_from", "contract_to",
                   "contract_no", "payment_frequency", "contract_pos", "contract_type",
                   "cost_center", "purchaser"]
```

Update hints to match:
```python
        hints = ["Optional (auto-generated if empty)",
                 "Required for regular PO; leave empty for independent FC PO",
                 "Optional (must exist if provided)",
                 "Optional", "Optional (defaults to importer)",
                 "FC or empty (only set 'FC' for independent FC PO without SC)",
                 "Required",
                 "active/finished (draft also allowed for FC PO)",
                 "YYYY-MM-DD", "YYYY-MM-DD", "Optional",
                 "monthly/quarterly/yearly", "Optional", "Optional", "Optional",
                 "Optional"]
```

Add a second sample row (row 5) demonstrating independent FC PO:
```python
        sample = ["[EXAMPLE]", "SC-0000000-20260601-001", "V-000001", "", "", "",
                  "50000", "active", "2026-01-01", "2026-12-31", "", "monthly", "", "", "", ""]
        sample2 = ["[EXAMPLE]", "", "V-000001", "", "", "FC",
                   "100000", "draft", "2026-01-01", "2026-12-31", "", "monthly", "", "", "", ""]
```

Update info text:
```python
        info_text = (
            "Import Rules: PO records with status \"active\" or \"finished\" can be imported "
            "(draft also allowed for independent FC POs with request_type=FC). "
            "Required fields: PO NO, PO Amount, Status. "
            "SC NO is required for regular POs; leave empty for independent FC PO (set request_type=FC). "
            "Leave PO ID empty to auto-generate."
        )
```

- [ ] **Step 6: Commit**

```bash
git add sc_gr_app/services/import_service.py sc_gr_app/api/bridge.py
git commit -m "feat: support independent FC PO in import validation, preview, INSERT, and template"
```

---

### Task 9: Notification — thresholds, schedules, monthly, sender

**Files:**
- Modify: `sc_gr_app/notification/thresholds.py`
- Modify: `sc_gr_app/notification/schedules.py`
- Modify: `sc_gr_app/notification/monthly.py`
- Modify: `sc_gr_app/notification/sender.py`

- [ ] **Step 1: Fix `thresholds.py` — LEFT JOIN + CASE + COALESCE requester_id**

At line 28, change:
```sql
           JOIN sc_records sc ON sc.sc_id = po.sc_id
```
to:
```sql
           LEFT JOIN sc_records sc ON sc.sc_id = po.sc_id
```

At line 20, change the SELECT to use explicit COALESCE for requester_id (avoiding fragile column-ordering behavior):
```sql
           SELECT po.*,
                  COALESCE(sc.requester_id, po.requester_id) as requester_id,
                  sc.request_type as sc_request_type,
```

At lines 21-26, change the remaining calculation:
```sql
                  po.po_amount - COALESCE(
                    CASE WHEN pos.request_type = 'FC' OR sc.request_type = 'FC'
                      THEN calloff_totals.allocated
                      ELSE gr_totals.con_value_total
                    END, 0
                  ) as remaining
```

At line 70, change (because requester_id is now explicit in SELECT):
```python
        requester_id = po["requester_id"]  # COALESCE(sc.requester_id, po.requester_id) from SELECT
```
This is already correct — the SELECT now explicitly provides the right value.

- [ ] **Step 2: Fix `schedules.py` — LEFT JOIN + COALESCE**

At lines 34-37, change:
```sql
           SELECT ncs.*, po.sc_id, sc.requester_id
           FROM notification_custom_schedule ncs
           JOIN pos po ON po.po_id = ncs.entity_id
           JOIN sc_records sc ON sc.sc_id = po.sc_id
```
to:
```sql
           SELECT ncs.*, po.sc_id, COALESCE(sc.requester_id, po.requester_id) as requester_id
           FROM notification_custom_schedule ncs
           JOIN pos po ON po.po_id = ncs.entity_id
           LEFT JOIN sc_records sc ON sc.sc_id = po.sc_id
```

- [ ] **Step 3: Fix `monthly.py` — LEFT JOIN + CASE + effective type in SELECT**

At line 74, change:
```sql
           JOIN sc_records sc ON sc.sc_id = p.sc_id
```
to:
```sql
           LEFT JOIN sc_records sc ON sc.sc_id = p.sc_id
```

At lines 66-72, change:
```sql
               CASE WHEN sc.request_type = 'FC'
                 THEN calloff_totals.allocated
                 ELSE (SELECT SUM(gr.con_value) FROM gr_requests gr
                       WHERE gr.po_id = p.po_id AND gr.status = 'approved')
               END
```
to:
```sql
               CASE WHEN p.request_type = 'FC' OR sc.request_type = 'FC'
                 THEN calloff_totals.allocated
                 ELSE (SELECT SUM(gr.con_value) FROM gr_requests gr
                       WHERE gr.po_id = p.po_id AND gr.status = 'approved')
               END
```

At the SELECT clause, add effective type for downstream use:
```sql
           SELECT ...,
               p.request_type as po_request_type,
               sc.request_type as sc_request_type,
               ...
```

- [ ] **Step 4: Fix `sender.py` — budget info for FC POs**

`_attach_budget_info()` (line 41) for `entity_type == "po"` computes `open_po_amount = po_amount - pending_gr - approved_gr`. For independent FC POs, this shows the full PO amount as "open" even when call-off SCs have consumed budget. Add call-off SC deduction.

After line 71 in sender.py (`entity_info["open_po_amount"] = po_amount - pending - approved`):

```python
        # Deduct call-off SC amounts for FC-type POs
        is_fc = entity_info.get("request_type") == "FC"
        if not is_fc and entity_info.get("sc_id"):
            sc_row = conn.execute(
                "SELECT request_type FROM sc_records WHERE sc_id = ?",
                (entity_info["sc_id"],),
            ).fetchone()
            is_fc = sc_row and sc_row["request_type"] == "FC"
        if is_fc:
            calloff_allocated = conn.execute(
                "SELECT COALESCE(SUM(sc_amount), 0) FROM sc_records WHERE calloff_po_id = ?",
                (entity_id,),
            ).fetchone()[0]
            entity_info["open_po_amount"] = max(0, po_amount - calloff_allocated)
```

**Note on pre-existing dead code (lines 108-110):** The second `elif entity_type == "po"` block that calls `_attach_child_grs()` is never reached (the first `if entity_type == "po"` at line 51 matches first). This is a pre-existing issue affecting all PO types, not specific to independent FC PO. Marked for separate cleanup but NOT part of this feature.

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/notification/thresholds.py sc_gr_app/notification/schedules.py sc_gr_app/notification/monthly.py sc_gr_app/notification/sender.py
git commit -m "fix: LEFT JOIN and FC type/budget detection in notification modules for independent FC PO"
```

---

### Task 10: api/bridge.py — New Endpoints + Permission Fixes

**Files:**
- Modify: `sc_gr_app/api/bridge.py`

- [ ] **Step 1: Add `get_po` endpoint (lightweight, for deep links)**

The `main.js` deep-link handler calls `callApi('get_po', { po_id })`. This endpoint doesn't exist. Add it:

```python
    def get_po(self, payload) -> dict:
        """Return basic PO info (for deep-link navigation)."""
        try:
            payload = self._required_payload(payload)
            self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            from sc_gr_app.db.connection import connect
            from sc_gr_app.errors import NotFound
            with connect(self.config) as conn:
                po = conn.execute(
                    "select po_id, sc_id, request_type, vendor_id, status, po_amount, "
                    "requester_id, po_no from pos where po_id = ?",
                    (po_id,),
                ).fetchone()
                if po is None:
                    raise NotFound(f"PO not found: {po_id}")
                return ok(_row_to_dict(po))
        except Exception as exc:
            return fail(exc)
```

- [ ] **Step 2: Add `get_po_detail` endpoint (rich, for detail page)**

Add a new endpoint for the PoDetailView independent mode:

```python
    def get_po_detail(self, payload) -> dict:
        """Return full PO detail including operations, call-off SCs, permissions."""
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            from sc_gr_app.db.connection import connect
            from sc_gr_app.errors import NotFound
            with connect(self.config) as conn:
                po = conn.execute(
                    """select po.*, v.vendor_name,
                       coalesce(po.request_type, sc.request_type) as sc_request_type,
                       sc.sc_no
                       from pos po
                       left join sc_records sc on sc.sc_id = po.sc_id
                       join vendors v on v.vendor_id = po.vendor_id
                       where po.po_id = ?""",
                    (po_id,),
                ).fetchone()
                if po is None:
                    raise NotFound(f"PO not found: {po_id}")
                po = _row_to_dict(po)

                ops = conn.execute(
                    "select * from operation_records where object_type = 'po' "
                    "and object_id = ? order by created_at desc",
                    (po_id,),
                ).fetchall()

                calloff_scs = []
                if po.get("sc_request_type") == "FC":
                    calloff_scs = conn.execute(
                        "select * from sc_records where calloff_po_id = ?", (po_id,)
                    ).fetchall()

                user_id = current_user["user_id"]
                is_owner = po.get("requester_id") == user_id
                is_admin = current_user.get("role") == "admin"
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
        except Exception as exc:
            return fail(exc)
```

- [ ] **Step 3: Fix `save_po_notification_config` — LEFT JOIN for independent FC PO**

At the permission check query (~lines 771-774), change from:
```sql
SELECT sc.requester_id FROM pos JOIN sc_records sc ON sc.sc_id = po.sc_id WHERE po.po_id = ?
```
to:
```sql
SELECT po.requester_id as po_requester, sc.requester_id as sc_requester
FROM pos po LEFT JOIN sc_records sc ON sc.sc_id = po.sc_id WHERE po.po_id = ?
```

Then update the permission check:
```python
            requester_id = po["sc_requester"] or po["po_requester"]
            if current_user.get("role") != "admin" and current_user.get("user_id") != requester_id:
                raise PermissionDenied("Only the owner or admin can modify notification settings")
```

- [ ] **Step 4: Fix `save_po_custom_schedules` — same pattern**

Apply the same LEFT JOIN + COALESCE fix as Step 3.

- [ ] **Step 5: Fix `_resolve_target_path` — handle null parent_sc_id**

At line 1509-1511, change:
```python
        elif entity_type == "po":
            pid = parent_sc_id or "unknown-sc"
            target_dir = base / "sc" / pid / "po" / entity_id
```
to:
```python
        elif entity_type == "po":
            if parent_sc_id:
                target_dir = base / "sc" / parent_sc_id / "po" / entity_id
            else:
                target_dir = base / "po" / entity_id
```

- [ ] **Step 6: Commit**

```bash
git add sc_gr_app/api/bridge.py
git commit -m "feat: add get_po/get_po_detail endpoints, fix permission checks and attachment path for independent FC PO"
```

---

### Task 11: Frontend Router + PoDetailView Dual-Mode Overhaul

**Files:**
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/views/PoDetailView.vue`

- [ ] **Step 1: Add independent PO route to router**

After the existing `po-detail` route, add:

```js
  {
    path: '/po/:poId',
    name: 'po-detail-independent',
    component: () => import('@/views/PoDetailView.vue'),
    meta: { layout: 'default', title: 'PO Detail' }
  },
```

- [ ] **Step 2: Rewrite PoDetailView script — dual-mode data loading**

Replace the `<script setup>` section with dual-mode support. The existing `calloffScs` ref and `loadCalloffData` function remain unchanged (used for SC-bound FC PO data loaded via `useSc.fetchDetail`).

Key new variables and computed properties:

```js
const hasSc = computed(() => !!route.params.scId)
const poDetail = ref(null)  // Data from get_po_detail for independent mode

const po = computed(() => {
  if (hasSc.value) {
    const pos = scDetail.value?.pos || []
    return pos.find(p => String(p.po_id) === String(poId.value)) || {}
  }
  return poDetail.value?.po || {}
})

const grs = computed(() => {
  if (!hasSc.value) return []
  const allGrs = scDetail.value?.grs || []
  return allGrs.filter(g => String(g.po_id) === String(poId.value))
})

const scVendors = computed(() => {
  if (hasSc.value) return scDetail.value?.vendors || []
  return vendorState.rows || []
})

const poOperationRecords = computed(() => {
  if (hasSc.value) {
    const logs = scDetail.value?.operation_records || []
    return logs.filter(l => l.object_type === 'po' && l.object_id === poId.value)
  }
  return poDetail.value?.operation_records || []
})

const permissions = computed(() => {
  if (hasSc.value) return scDetail.value?.permissions || {}
  return poDetail.value?.permissions || {}
})

const isRequester = computed(() => {
  if (hasSc.value) return window.__currentUser?.user_id === scDetail.value?.sc?.requester_id
  return window.__currentUser?.user_id === po.value?.requester_id
})

// calloffScs: existing ref used for SC-bound mode (populated by loadCalloffData).
// For independent mode, use poDetail.calloff_scs directly.
const calloffScs = computed(() => {
  if (hasSc.value) return calloffScsData.value  // existing ref
  return poDetail.value?.calloff_scs || []
})
```

- [ ] **Step 3: Rewrite `onMounted` — dual-mode loading**

```js
onMounted(async () => {
  try { activeUsers.value = await callApi('list_users') } catch {}
  await searchVendors()

  if (hasSc.value) {
    await fetchDetail(scId.value)
    await loadCalloffData()
    if (poId.value) {
      try { await fetchPoConfig(poId.value) } catch {}
      try { await fetchCustomSchedules(poId.value) } catch {}
    }
  } else {
    try {
      const result = await callApi('get_po_detail', { po_id: poId.value })
      poDetail.value = result
    } catch (e) {
      ElMessage.error(e.message || 'Failed to load PO detail')
    }
    if (poId.value) {
      try { await fetchPoConfig(poId.value) } catch {}
      try { await fetchCustomSchedules(poId.value) } catch {}
    }
  }
})
```

- [ ] **Step 4: Add `refreshDetail` helper and replace all `fetchDetail(scId.value)` calls**

```js
async function refreshDetail() {
  if (hasSc.value) {
    await fetchDetail(scId.value)
  } else {
    try {
      const result = await callApi('get_po_detail', { po_id: poId.value })
      poDetail.value = result
    } catch (e) {
      ElMessage.error(e.message || 'Failed to refresh PO detail')
    }
  }
}
```

Replace `await fetchDetail(scId.value)` with `await refreshDetail()` in: `handleEditSave`, `handleFinish`, `handleRecall`, `handleSubmit`, `handleCalloffScSave`, `handleGrApprove`, `handleGrDeny`, `handleGrSubmit`, `handleGrFinish`, `handleGrSave`, `handleGrSaveDraft`.

- [ ] **Step 5: Update template — SC section conditional, permissions, attachments**

- Lines 9-17 (header buttons): Replace `scDetail?.permissions?.can_manage_po` with `permissions?.can_manage_po`, `scDetail?.permissions?.can_delete_po` with `permissions?.can_delete_po`.
- Lines 28, 31 (Add GR / Add Call-off SC buttons): Replace `scDetail?.permissions` with `permissions`.
- Lines 36-41 (SC info section): Wrap in `<template v-if="hasSc">`.
- Line 93 (call-off SC Add button in FC section): Replace `scDetail?.permissions` with `permissions`.
- Line 118 (AttachmentList): `:parent-sc-id="hasSc ? scId : null"`.
- Line 120 (AttachmentList @changed): `@changed="refreshDetail"`.
- Lines 161, 163 (AttachmentDialog): `:parent-sc-id="hasSc ? scId : null"`, `@changed="refreshDetail"`.
- Line 344 (delete redirect): Change to:
  ```js
    if (hasSc.value) {
      router.replace(`/sc/${scId.value}`)
    } else {
      router.replace('/po')
    }
  ```
- In `handleEditSave`, `handleGrSave`, `handleGrSaveDraft`: change `parent_sc_id: scId.value` to `parent_sc_id: hasSc.value ? scId.value : null`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/router/index.js frontend/src/views/PoDetailView.vue
git commit -m "feat: add independent PO route and dual-mode PoDetailView"
```

---

### Task 12: Frontend PoListView — Split Create PO Button

**Files:**
- Modify: `frontend/src/views/PoListView.vue`

- [ ] **Step 1: Replace "New PO" button with dropdown**

Change the single "New PO" button to a split-button dropdown:

```html
      <el-dropdown @command="handleCreatePoCommand" style="margin-right:8px">
        <el-button type="primary">
          <el-icon><Plus /></el-icon> {{ $t('po.addPo') }} <el-icon><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="regular">{{ $t('po.newRegularPo') }}</el-dropdown-item>
            <el-dropdown-item command="fc">{{ $t('po.newFcPo') }}</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
```

Import `ArrowDown` from `@element-plus/icons-vue`.

- [ ] **Step 2: Add command handler and `openCreateFcPoDialog`**

```js
function handleCreatePoCommand(command) {
  if (command === 'regular') {
    openCreatePoDialog()  // existing function — SC selection dialog
  } else if (command === 'fc') {
    openCreateFcPoDialog()
  }
}

async function openCreateFcPoDialog() {
  selectedScId.value = ''
  selectedScRecord.value = null
  scSelectVisible.value = false
  // Load all vendors (no SC vendor filter for FC PO)
  try {
    const result = await callApi('search_vendors', { limit: 500 })
    scLinkedVendors.value = result.rows || []
  } catch { scLinkedVendors.value = [] }
  poDialogMode.value = 'create'
  poDialogRecord.value = null
  poDialogVisible.value = true
}
```

Note: `scLinkedVendors` is the reactive variable passed to PoFormDialog's `vendors` prop. For regular PO, it's populated by SC selection dialog. For FC PO, we load all vendors directly.

- [ ] **Step 3: Update `handlePoSave` — omit sc_id for FC PO, add request_type**

```js
async function handlePoSave(data) {
  try {
    const { _attachments, ...formData } = data
    const isFcPo = !selectedScRecord.value
    const payload = { ...formData }
    if (isFcPo) {
      payload.request_type = 'FC'
      // sc_id intentionally omitted
    } else {
      payload.sc_id = selectedScRecord.value?.sc_id || formData.sc_id
    }
    const created = await createPo(payload)
    if (_attachments?.length) {
      await callApi('add_attachments', {
        entity_type: 'po', entity_id: created.po_id,
        file_paths: _attachments, parent_sc_id: created.sc_id || null
      })
    }
    ElMessage.success(t('common.saved'))
    poDialogVisible.value = false
    await searchPos()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}
```

- [ ] **Step 4: Update `handlePoSaveDraft` — same pattern**

```js
async function handlePoSaveDraft(data) {
  try {
    const { _attachments, ...formData } = data
    const isFcPo = !selectedScRecord.value
    const payload = { ...formData, status: 'draft' }
    if (isFcPo) {
      payload.request_type = 'FC'
    } else {
      payload.sc_id = selectedScRecord.value?.sc_id || formData.sc_id
    }
    const created = await createPo(payload)
    if (_attachments?.length) {
      await callApi('add_attachments', {
        entity_type: 'po', entity_id: created.po_id,
        file_paths: _attachments, parent_sc_id: created.sc_id || null
      })
    }
    ElMessage.success(t('po.draftSaved'))
    poDialogVisible.value = false
    await searchPos()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}
```

- [ ] **Step 5: Update PoTable detail click — branch on sc_id**

In the PoTable component's `@detail` event handler, change:
```js
row => $router.push(`/sc/${row.sc_id}/po/${row.po_id}`)
```
to:
```js
row => row.sc_id
  ? $router.push(`/sc/${row.sc_id}/po/${row.po_id}`)
  : $router.push(`/po/${row.po_id}`)
```

- [ ] **Step 6: Add i18n keys**

Add to locale files:
- EN: `"newRegularPo": "New Regular PO"`, `"newFcPo": "New FC PO"`
- ZH: `"newRegularPo": "新建常规PO"`, `"newFcPo": "新建FC PO"`

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/PoListView.vue frontend/src/i18n/
git commit -m "feat: split-button for PO creation, FC PO save omits sc_id"
```

---

### Task 13: Frontend AppHeader, main.js, HomeView

**Files:**
- Modify: `frontend/src/components/layout/AppHeader.vue`
- Modify: `frontend/src/main.js`
- Modify: `frontend/src/views/HomeView.vue`

- [ ] **Step 1: Fix AppHeader breadcrumbs for `po-detail-independent`**

Add breadcrumb mapping for the new route:

```js
    'po-detail-independent': [
      { i18nKey: 'breadcrumb.poList', to: '/po' },
      { i18nKey: 'breadcrumb.poDetail', to: '' }
    ],
```

- [ ] **Step 2: Fix main.js deep links — branch on sc_id**

At lines 22-24, change:
```js
  } else if (params.type === 'po') {
    const po = await callApi('get_po', { po_id: params.id })
    router.push(`/sc/${po.sc_id}/po/${params.id}`)
```
to:
```js
  } else if (params.type === 'po') {
    const po = await callApi('get_po', { po_id: params.id })
    if (po.sc_id) {
      router.push(`/sc/${po.sc_id}/po/${params.id}`)
    } else {
      router.push(`/po/${params.id}`)
    }
```

- [ ] **Step 3: Fix HomeView workbench PO clicks — lines 181 and 203**

Change:
```html
@click="$router.push(`/sc/${row.sc_id}/po/${row.po_id}`)"
```
to:
```html
@click="row.sc_id ? $router.push(`/sc/${row.sc_id}/po/${row.po_id}`) : $router.push(`/po/${row.po_id}`)"
```

Note: Lines 65 and 244 are GR click handlers — GRs always have non-null sc_id from call-off SCs. No change needed.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/layout/AppHeader.vue frontend/src/main.js frontend/src/views/HomeView.vue
git commit -m "fix: navigation breadcrumbs and deep links for independent FC PO"
```

---

### Task 14: Integration Testing

- [ ] **Step 1: Test backend — create independent FC PO**

```python
result = callApi('create_po', {
    vendor_id: 'V-000001',
    po_amount: 100000,
    request_type: 'FC',
    contract_from: '2026-07-01',
    contract_to: '2027-06-30',
})
# Expected: { ok: true, po: { sc_id: null, request_type: 'FC', status: 'draft' } }
```

- [ ] **Step 2: Test submit independent FC PO → active**

```python
callApi('submit_po', { po_id: '<created_po_id>' })
# Expected: status = 'active'
```

- [ ] **Step 3: Test call-off SC creation under independent FC PO (critical bug fix)**

```python
callApi('create_sc_draft', {
    calloff_po_id: '<fc_po_id>',
    sc_no: 'TEST-CO-001',
    sc_amount: 50000,
    vendor_id: 'V-000002',
    requester_id: current_user.user_id,
    # ... other required fields
})
# Expected: success (was the _validate_calloff_po crash bug)
```

- [ ] **Step 4: Test budget enforcement — call-off total must not exceed PO(FC) amount**

```python
# Create a second call-off SC that would exceed the total
callApi('create_sc_draft', {
    calloff_po_id: '<fc_po_id>',
    sc_amount: 60000,  # 50000 + 60000 = 110000 > 100000
    # ...
})
# Expected: ConflictError "Call-off SC total would exceed PO(FC) amount"
```

- [ ] **Step 5: Test finish — block if non-final call-offs exist**

```python
callApi('finish_po', { po_id: '<fc_po_id>' })
# Expected: ConflictError about non-final call-off SCs
```

- [ ] **Step 6: Test GR blocking — verify defense-in-depth**

```python
# Create GR under a call-off SC's regular PO (normal flow — should work)
# Verify the FC gate in create_gr rejects attempts at FC PO level
```

- [ ] **Step 7: Test visibility — non-owner can't see independent FC PO**

Log in as a different requester (not owner, not admin). Search for the FC PO via `search_pos`. Expected: PO not in results.

- [ ] **Step 8: Test frontend — PoDetailView independent mode**

Navigate to `/po/<fc_po_id>`. Verify: PO detail renders, SC section hidden, Edit/Submit/Finish/Delete buttons work, "New Call-off SC" button visible, GR section hidden, breadcrumbs show "PO List → PO Detail".

- [ ] **Step 9: Test frontend — PoListView creates FC PO**

Click "New PO" dropdown → "New FC PO". Verify: PoFormDialog opens without SC selection, all vendors available, save creates PO with request_type='FC' and no sc_id, detail link uses `/po/<id>`.

- [ ] **Step 10: Run existing test suite**

```bash
cd sc_gr_app && python -m pytest tests/ -v
```

Fix any regressions.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "test: integration verification for independent FC PO feature"
```

---

## Files Confirmed Safe (No Changes Required)

The following modules were thoroughly reviewed and found to need zero changes:

| Module | Reason |
|---|---|
| `vendor_service.py` | Only `SELECT count(*) FROM pos WHERE vendor_id = ?` for delete check. No sc_id. |
| `record_service.py` | `sc_id` accepted as call-time parameter, stored as-is. No pos/sc_records queries. |
| `lock_service.py` | Filesystem-based advisory locks. Zero SQL queries. |
| `rbac.py` | Pure function decorators. No queries. |
| `connection.py` | Pure `connect()` factory. No queries. |
| `user_service.py` | No pos/sc_records queries. |
| `notification_service.py` (services/) | `queue_status_change` for PO entity_type uses `po_id` directly. No sc_id dependency. |
| `notification/config.py` | `get_entity_config` by `entity_type` + `entity_id` (po_id). No sc_id. |
| `notification/queue.py` | All operations by entity_type + entity_id (po_id). No sc_id. |
| `notification/templates.py` | Pure formatting. `sc_id` renders as `-` for null (cosmetic, acceptable). |
| `notification/engine.py` / `__main__.py` | Orchestration only. No direct queries. |
| `GrDetailView.vue` | Always has non-null scId from call-off SC route. Parent PO link valid. |
| `ScDetailView.vue` | Independent FC PO has no SC parent. Not affected. |
| `PoTable.vue` | Handles null `sc_id` gracefully (`shortId(null)` returns `-`). |
| `PoFormDialog.vue` | Zero references to sc_id, request_type. Pure form. Parents control API payload. |
| `usePo.js`, `useSc.js`, `useGr.js`, `useNotification.js`, `useVendor.js`, `useExport.js` | API callers only. No sc_id logic. |
| `GrListView.vue`, `MailView.vue`, `EmailLogsView.vue`, `EmailPreviewDialog.vue` | No sc_id dependency. |
| `PoNotificationCard.vue`, `PoCustomScheduleCard.vue`, `NotificationDefaults.vue` | Use po_id directly. No sc_id. |

## Pre-existing Issues Noted (Not Caused By This Feature)

- **sender.py lines 108-110:** Dead code — second `elif entity_type == "po"` block unreachable. `_attach_child_grs()` never called for any PO type. Separate cleanup item.
- **sender.py `_attach_budget_info` for PO-level emails:** Uses GR-only calculation for `open_po_amount` which is inaccurate for FC POs with call-off SCs. Fixed in Task 9 Step 4.
