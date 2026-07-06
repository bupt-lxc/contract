# Last Delivery GR — auto-finish PO cascade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a Last Delivery GR is finished, cascade-finish all other approved GRs under the same PO and auto-finish the PO in one transaction.

**Architecture:** Single-transaction cascade in `finish_gr` with a `confirm_cascade` two-step protocol: first call returns `{needs_cascade: true, grs_to_finish: [...]}` (via `ok()` so frontend `callApi` passes it through), second call with `confirm_cascade=True` executes the full cascade. Extract `_finish_po_in_transaction` helper from `finish_po` to avoid lock re-entrancy. Enforce last_delivery uniqueness at create/update time.

**Tech Stack:** Python (sqlite3), Vue 3 + Element Plus, pytest

---

### Task 1: Database migration — add `finished_by` to `pos`

**Files:**
- Modify: `sc_gr_app/db/migrations.py`

- [ ] **Step 1: Bump schema version and add migration function**

Change `SCHEMA_VERSION = 32` → `SCHEMA_VERSION = 33` at line 9.

After `_migrate_v32` (which ends around line 1349), add the v33 migration function:

```python
def _migrate_v33(conn) -> None:
    """Add finished_by column to pos table for PO finish audit trail."""
    if _table_exists(conn, "pos"):
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(pos)")}
        if "finished_by" not in existing:
            conn.execute("ALTER TABLE pos ADD COLUMN finished_by TEXT REFERENCES users(user_id)")
    _record(conn, 33)
```

In the `migrate` function, after the v32 block (around line 1527, after `conn.commit()` for v32), add:

```python
            if 33 not in _applied_versions(conn):
                conn.execute("BEGIN")
                _migrate_v33(conn)
                conn.commit()
```

- [ ] **Step 2: Commit**

```bash
git add sc_gr_app/db/migrations.py
git commit -m "feat: add finished_by column to pos table (migration v33)"
```

---

### Task 2: Add `conflicts` support to `ConflictError` and update `fail()` / `callApi`

**Files:**
- Modify: `sc_gr_app/errors.py`
- Modify: `sc_gr_app/api/schemas.py`
- Modify: `frontend/src/api/bridge.js`

- [ ] **Step 1: Add `conflicts` parameter to `ConflictError`**

In `sc_gr_app/errors.py`, replace the `ConflictError` class:

```python
class ConflictError(AppError):
    code = "CONFLICT_ERROR"

    def __init__(self, message: str, conflicts: list = None):
        super().__init__(message)
        self.conflicts = conflicts
```

- [ ] **Step 2: Update `fail()` in schemas.py to include conflicts**

In `sc_gr_app/api/schemas.py`, replace the `fail` function:

```python
def fail(exc: Exception) -> dict:
    if isinstance(exc, AppError):
        code = exc.code
        message = exc.message
    else:
        code = "UNEXPECTED_ERROR"
        message = str(exc) or "Unexpected application error"

    result = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if isinstance(exc, AppError) and hasattr(exc, 'conflicts') and exc.conflicts:
        result["conflicts"] = exc.conflicts
    return result
```

- [ ] **Step 3: Update frontend `ApiError` to carry `conflicts`**

In `frontend/src/api/bridge.js`, replace the `ApiError` class and error handling:

```javascript
class ApiError extends Error {
  constructor(error) {
    super(error.message || 'API error')
    this.code = error.code || 'UNKNOWN'
    this.conflicts = error.conflicts || null
  }
}
```

And update the `if (!result.ok)` block (around line 26-28):

```javascript
    if (!result.ok) {
      const err = new ApiError(result.error)
      if (result.conflicts) err.conflicts = result.conflicts
      throw err
    }
```

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/errors.py sc_gr_app/api/schemas.py frontend/src/api/bridge.js
git commit -m "feat: add conflicts support to ConflictError, fail(), and ApiError"
```

---

### Task 3: Extract `_finish_po_in_transaction` helper from `finish_po`

**Files:**
- Modify: `sc_gr_app/services/po_service.py`

- [ ] **Step 1: Add `_finish_po_in_transaction` helper**

Add this function in `po_service.py`, before the existing `finish_po`:

```python
def _finish_po_in_transaction(conn, po_id: str, current_user: dict, timestamp: str) -> dict:
    """Finish a PO within an existing transaction. Must NOT acquire locks."""
    before = _get_po_or_raise(conn, po_id)

    sc = conn.execute(
        "select status from sc_records where sc_id = ?",
        (before["sc_id"],),
    ).fetchone()
    if sc and sc["status"] == "finished":
        raise ConflictError("Finished SC cannot be edited")
    if before["status"] != "active":
        raise ConflictError("PO must be active")

    conn.execute(
        """
        update pos
        set status = 'finished',
            updated_at = ?,
            finished_at = ?,
            finished_by = ?
        where po_id = ?
        """,
        (timestamp, timestamp, current_user["user_id"], po_id),
    )
    after = _get_po_or_raise(conn, po_id)

    write_operation_record(
        conn,
        action_type="finish_po",
        object_type="po",
        object_id=po_id,
        sc_id=before["sc_id"],
        operator_id=current_user["user_id"],
        machine_id=current_user["machine_id"],
        before=before,
        after=after,
    )
    notification_service.queue_status_change(
        conn, "po", po_id, "finish",
        {"requester_id": sc["requester_id"]} if sc else {}, current_user
    )
    return after
```

- [ ] **Step 2: Refactor `finish_po` to delegate to the helper**

Replace the body of `finish_po` (keep lock acquisition + FC/GR checks, delegate to helper):

```python
def finish_po(config: AppConfig, current_user: dict, po_id: str) -> dict:
    require_requester_or_admin(current_user)

    with connect(config) as lookup_conn:
        sc_id = _get_po_or_raise(lookup_conn, po_id)["sc_id"]

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)

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
                    non_final_grs = conn.execute(
                        """
                        SELECT gr_id, status FROM gr_requests
                        WHERE po_id = ? AND status NOT IN ('denied', 'finished')
                        """,
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

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/services/po_service.py
git commit -m "refactor: extract _finish_po_in_transaction helper from finish_po"
```

---

### Task 4: Add `last_delivery` validation and uniqueness constraint

**Files:**
- Modify: `sc_gr_app/services/gr_service.py`

- [ ] **Step 1: Add validation helpers in `gr_service.py`**

Add these two functions after the existing `_validate_user_exists`:

```python
def _validate_last_delivery_value(value) -> None:
    """Validate last_delivery is 'Y', 'N', or empty/None."""
    if value is not None and value != "" and value not in ("Y", "N"):
        raise ValidationError("last_delivery must be 'Y' or 'N'")


def _validate_last_delivery_unique(conn, po_id: str, exclude_gr_id: str = None) -> None:
    """Ensure no other active GR under the same PO is marked as Last Delivery."""
    rows = conn.execute(
        """
        SELECT gr_id FROM gr_requests
        WHERE po_id = ? AND last_delivery = 'Y'
          AND status NOT IN ('denied', 'finished')
          AND (? IS NULL OR gr_id != ?)
        """,
        (po_id, exclude_gr_id, exclude_gr_id or ""),
    ).fetchall()
    if rows:
        raise ConflictError(
            f"GR {rows[0]['gr_id']} under this PO is already marked as Last Delivery"
        )
```

- [ ] **Step 2: Add validation in `create_gr`**

In `create_gr`, after `_validate_gr_creation_context` call and before the INSERT, add:

```python
                _validate_last_delivery_value(data.get("last_delivery"))
                if data.get("last_delivery") == "Y":
                    _validate_last_delivery_unique(conn, po_id)
```

- [ ] **Step 3: Add validation in `update_gr`**

In `update_gr`, in the draft/pending branch (the first `allowed` dict), after the existing validations and before the UPDATE, add:

```python
                    _validate_last_delivery_value(allowed.get("last_delivery"))
                    if "last_delivery" in allowed and allowed["last_delivery"] == "Y":
                        _validate_last_delivery_unique(conn, merged["po_id"], gr_id)
```

Also in the approved branch (the second `allowed` dict), after `if not allowed`, add:

```python
                    _validate_last_delivery_value(allowed.get("last_delivery"))
                    if "last_delivery" in allowed and allowed["last_delivery"] == "Y":
                        _validate_last_delivery_unique(conn, before["po_id"], gr_id)
```

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/services/gr_service.py
git commit -m "feat: add last_delivery value validation and uniqueness constraint"
```

---

### Task 5: Add cascade logic to `finish_gr`

**Files:**
- Modify: `sc_gr_app/services/gr_service.py`

- [ ] **Step 1: Replace `finish_gr` with cascade-aware version**

Replace the existing `finish_gr` function (lines 859-912) with:

```python
def finish_gr(config: AppConfig, current_user: dict, gr_id: str,
              confirm_cascade: bool = False) -> dict:
    """Mark an approved GR as finished. If Last Delivery, cascade-finish PO."""
    require_requester_or_admin(current_user)

    with connect(config) as lookup_conn:
        sc_id = _get_gr_sc_id(lookup_conn, gr_id)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                _require_editable_parent_sc(conn, sc_id)
                before = _get_gr(conn, gr_id)
                if before["status"] != "approved":
                    raise ConflictError("GR must be approved")

                if before.get("last_delivery") != "Y":
                    # Non-LD GR: normal finish (confirm_cascade silently ignored)
                    timestamp = utc_now()
                    conn.execute(
                        """
                        update gr_requests
                        set status = 'finished',
                            finished_by = ?,
                            finished_at = ?,
                            updated_at = ?
                        where gr_id = ?
                        """,
                        (current_user["user_id"], timestamp, timestamp, gr_id),
                    )
                    after = _get_gr(conn, gr_id)
                    write_operation_record(
                        conn,
                        action_type="finish_gr",
                        object_type="gr",
                        object_id=gr_id,
                        sc_id=sc_id,
                        operator_id=current_user["user_id"],
                        machine_id=current_user["machine_id"],
                        before=before,
                        after=after,
                    )
                    sc = conn.execute(
                        "SELECT requester_id FROM sc_records WHERE sc_id = ?",
                        (sc_id,),
                    ).fetchone()
                    notification_service.queue_status_change(
                        conn, "gr", gr_id, "finish",
                        {"requester_id": sc["requester_id"]} if sc else {}, current_user
                    )
                    conn.commit()
                    return after

                # Last Delivery GR — cascade logic
                po_id = before["po_id"]
                all_other_grs = conn.execute(
                    """
                    SELECT gr_id, status FROM gr_requests
                    WHERE po_id = ? AND gr_id != ?
                    """,
                    (po_id, gr_id),
                ).fetchall()

                problematic = [
                    {"gr_id": r["gr_id"], "status": r["status"]}
                    for r in all_other_grs
                    if r["status"] in ("draft", "manager_confirm", "pending", "denied")
                ]
                approved_nf_ids = [
                    r["gr_id"]
                    for r in all_other_grs
                    if r["status"] == "approved"
                ]

                if problematic:
                    raise ConflictError(
                        f"Cannot finish Last Delivery GR: "
                        + ", ".join(f"{c['gr_id']}({c['status']})" for c in problematic),
                        conflicts=problematic,
                    )

                if not confirm_cascade:
                    # Return needs_cascade dict — goes through ok() in bridge,
                    # so callApi returns it as the data object directly
                    conn.commit()  # no changes made, but clean exit
                    return {
                        "needs_cascade": True,
                        "grs_to_finish": approved_nf_ids,
                    }

                # confirm_cascade=True: execute the full cascade
                shared_ts = utc_now()

                # 1. Finish approved (non-LD) GRs — no notifications
                for cascade_gr_id in approved_nf_ids:
                    gr_before = _get_gr(conn, cascade_gr_id)
                    if gr_before["status"] != "approved":
                        raise ConflictError(
                            f"GR {cascade_gr_id} status changed to {gr_before['status']}",
                            conflicts=[{"gr_id": cascade_gr_id, "status": gr_before["status"]}],
                        )
                    conn.execute(
                        """
                        update gr_requests
                        set status = 'finished',
                            finished_by = ?,
                            finished_at = ?,
                            updated_at = ?
                        where gr_id = ?
                        """,
                        (current_user["user_id"], shared_ts, shared_ts, cascade_gr_id),
                    )
                    gr_after = _get_gr(conn, cascade_gr_id)
                    write_operation_record(
                        conn,
                        action_type="finish_gr",
                        object_type="gr",
                        object_id=cascade_gr_id,
                        sc_id=sc_id,
                        operator_id=current_user["user_id"],
                        machine_id=current_user["machine_id"],
                        before=gr_before,
                        after=gr_after,
                    )

                # 2. Finish THIS (LD) GR — with notification
                conn.execute(
                    """
                    update gr_requests
                    set status = 'finished',
                        finished_by = ?,
                        finished_at = ?,
                        updated_at = ?
                    where gr_id = ?
                    """,
                    (current_user["user_id"], shared_ts, shared_ts, gr_id),
                )
                primary_gr_after = _get_gr(conn, gr_id)
                write_operation_record(
                    conn,
                    action_type="finish_gr",
                    object_type="gr",
                    object_id=gr_id,
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=primary_gr_after,
                )
                sc = conn.execute(
                    "SELECT requester_id FROM sc_records WHERE sc_id = ?",
                    (sc_id,),
                ).fetchone()
                notification_service.queue_status_change(
                    conn, "gr", gr_id, "finish",
                    {"requester_id": sc["requester_id"]} if sc else {}, current_user
                )

                # 3. Finish PO
                from sc_gr_app.services.po_service import _finish_po_in_transaction
                po_after = _finish_po_in_transaction(conn, po_id, current_user, shared_ts)

                conn.commit()

                return {
                    "gr": primary_gr_after,
                    "cascaded_grs": approved_nf_ids,
                    "po_finished": po_id,
                }

            except Exception:
                conn.rollback()
                raise
```

- [ ] **Step 2: Commit**

```bash
git add sc_gr_app/services/gr_service.py
git commit -m "feat: add Last Delivery cascade logic to finish_gr"
```

---

### Task 6: Update API Bridge for `finish_gr`

**Files:**
- Modify: `sc_gr_app/api/bridge.py`

- [ ] **Step 1: Update `finish_gr` bridge method**

Replace the `finish_gr` method (around line 460-469) with:

```python
    def finish_gr(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            gr_id = _require_payload_field(payload, "gr_id")
            confirm_cascade = payload.get("confirm_cascade", False)
            result = gr_service.finish_gr(self.config, current_user, gr_id, confirm_cascade)

            if isinstance(result, dict) and "needs_cascade" in result:
                # LD GR needs cascade confirmation — return directly (ok:true, data has needs_cascade)
                return ok(result)
            elif isinstance(result, dict) and "gr" in result:
                # Cascade executed: result = {"gr": ..., "cascaded_grs": [...], "po_finished": "..."}
                primary_gr = _format_entity_timestamps(result["gr"])
                self._auto_open_outlook_draft("gr", gr_id, "finish")
                self._auto_open_outlook_draft("po", result["po_finished"], "finish")
                return ok({
                    "data": primary_gr,
                    "cascaded_grs": result["cascaded_grs"],
                    "po_finished": result["po_finished"],
                })
            else:
                # Normal finish: result is the GR dict
                self._auto_open_outlook_draft("gr", gr_id, "finish")
                return ok(_format_entity_timestamps(result))
        except Exception as exc:
            return fail(exc)
```

- [ ] **Step 2: Commit**

```bash
git add sc_gr_app/api/bridge.py
git commit -m "feat: handle cascade needs_cascade and cascade success in bridge"
```

---

### Task 7: Fix import service `last_delivery` parse bug

**Files:**
- Modify: `sc_gr_app/services/import_service.py`

- [ ] **Step 1: Fix line 635**

Change line 635 from:
```python
parse_date(row.get("last_delivery")),
```
to:
```python
row.get("last_delivery"),
```

- [ ] **Step 2: Commit**

```bash
git add sc_gr_app/services/import_service.py
git commit -m "fix: stop parsing last_delivery as date in GR import"
```

---

### Task 8: Update frontend `useGr.js` composable

**Files:**
- Modify: `frontend/src/composables/useGr.js`

- [ ] **Step 1: Update `finishGr` to accept `confirmCascade` and return the result**

Change line 44 from:
```javascript
  async function finishGr(grId) { await callApi('finish_gr', { gr_id: grId }) }
```
to:
```javascript
  async function finishGr(grId, confirmCascade = false) {
    return await callApi('finish_gr', { gr_id: grId, confirm_cascade: confirmCascade })
  }
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/composables/useGr.js
git commit -m "feat: add confirmCascade parameter to finishGr composable"
```

---

### Task 9: Update `GrDetailView.vue` `handleFinish` for cascade

**Files:**
- Modify: `frontend/src/views/GrDetailView.vue`
- Modify: `frontend/src/i18n/locales/zh-CN.js`
- Modify: `frontend/src/i18n/locales/en-US.js`

- [ ] **Step 1: Add i18n keys**

In `zh-CN.js`, find the `gr` section and add:

```javascript
    lastDeliveryCascadeTitle: '最后交付确认',
    lastDeliveryCascadeMessage: '此 GR 为最后交付，以下 GR 将被一并完成：{list}。完成后 PO 也将自动完成。是否继续？',
    lastDeliveryNoCascadeMessage: '此 GR 为最后交付。完成后 PO 也将自动完成。是否继续？',
    grAndPoFinished: 'GR 已完成，PO 已自动完成',
```

In `en-US.js`, find the `gr` section and add:

```javascript
    lastDeliveryCascadeTitle: 'Last Delivery Confirmation',
    lastDeliveryCascadeMessage: 'This GR is the last delivery. The following GRs will also be finished: {list}. The PO will be finished afterwards. Continue?',
    lastDeliveryNoCascadeMessage: 'This GR is the last delivery. The PO will be finished afterwards. Continue?',
    grAndPoFinished: 'GR finished, PO auto-finished',
```

- [ ] **Step 2: Replace `handleFinish` in `GrDetailView.vue`**

Replace the existing `handleFinish` (lines 234-243) with:

```javascript
async function handleFinish() {
  try {
    await ElMessageBox.confirm(t('gr.finishGrConfirm'), t('gr.finishGr'), { type: 'warning' })
    const result = await finishGr(grId.value, false)
    
    if (result.needs_cascade) {
      const grsToFinish = result.grs_to_finish || []
      const message = grsToFinish.length > 0
        ? t('gr.lastDeliveryCascadeMessage', { list: grsToFinish.join(', ') })
        : t('gr.lastDeliveryNoCascadeMessage')
      await ElMessageBox.confirm(message, t('gr.lastDeliveryCascadeTitle'), {
        type: 'warning',
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
      })
      await finishGr(grId.value, true)
      ElMessage.success(t('gr.grAndPoFinished'))
    } else {
      ElMessage.success(t('gr.grFinished'))
    }
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/GrDetailView.vue frontend/src/i18n/locales/zh-CN.js frontend/src/i18n/locales/en-US.js
git commit -m "feat: handle Last Delivery cascade confirmation in GrDetailView"
```

---

### Task 10: Update `PoDetailView.vue` `handleGrFinish` for cascade

**Files:**
- Modify: `frontend/src/views/PoDetailView.vue`

- [ ] **Step 1: Replace `handleGrFinish` in `PoDetailView.vue`**

Replace the existing `handleGrFinish` (lines 424-433) with:

```javascript
async function handleGrFinish(row) {
  try {
    await ElMessageBox.confirm(t('gr.finishGrConfirm'), t('gr.finishGr'), { type: 'warning' })
    const result = await finishGr(row.gr_id, false)
    
    if (result.needs_cascade) {
      const grsToFinish = result.grs_to_finish || []
      const message = grsToFinish.length > 0
        ? t('gr.lastDeliveryCascadeMessage', { list: grsToFinish.join(', ') })
        : t('gr.lastDeliveryNoCascadeMessage')
      await ElMessageBox.confirm(message, t('gr.lastDeliveryCascadeTitle'), {
        type: 'warning',
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
      })
      await finishGr(row.gr_id, true)
      ElMessage.success(t('gr.grAndPoFinished'))
    } else {
      ElMessage.success(t('gr.grFinished'))
    }
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/PoDetailView.vue
git commit -m "feat: handle Last Delivery cascade confirmation in PoDetailView"
```

---

### Task 11: Write backend unit tests

**Files:**
- Modify: `tests/test_gr_service.py`

- [ ] **Step 1: Add test helper for creating GRs in various states**

After the `_setup_approved_sc_with_active_po` helper, add:

```python
def _create_gr(app_config, current_user, po_id, status="approved",
               last_delivery=None, estimated_amount=1000):
    """Create a GR with given status under the given PO. Returns GR dict."""
    from sc_gr_app.services.gr_service import create_gr, submit_gr, approve_gr
    data = {
        "po_id": po_id,
        "requester_id": current_user["user_id"],
        "estimated_amount": estimated_amount,
        "gr_no": f"GR-NO-TEST-{status}",
    }
    if last_delivery is not None:
        data["last_delivery"] = last_delivery

    gr = create_gr(app_config, current_user, data)
    if status in ("manager_confirm", "pending", "approved"):
        gr = submit_gr(app_config, current_user, gr["gr_id"])
    if status in ("pending", "approved"):
        admin = {"user_id": "admin", "role": "admin", "machine_id": "ADMIN01"}
        gr = confirm_gr(app_config, admin, gr["gr_id"])
    if status == "approved":
        admin = {"user_id": "admin", "role": "admin", "machine_id": "ADMIN01"}
        gr = approve_gr(app_config, admin, gr["gr_id"], con_value=estimated_amount)
    return gr


def _create_finished_gr(app_config, admin, user, po_id, last_delivery=None):
    """Create and finish a GR. Returns GR dict."""
    gr = _create_gr(app_config, user, po_id, status="approved", last_delivery=last_delivery)
    return finish_gr(app_config, user, gr["gr_id"])


def _create_denied_gr(app_config, admin, user, po_id, last_delivery=None):
    """Create and deny a GR. Returns GR dict."""
    gr = _create_gr(app_config, user, po_id, status="pending", last_delivery=last_delivery)
    return deny_gr(app_config, admin, gr["gr_id"])
```

- [ ] **Step 2: Add uniqueness tests**

```python
class TestLastDeliveryUniqueness:
    def test_create_gr_with_ld_no_conflict(self, app_config):
        admin, requester = _resolve_users(app_config)
        sc, po = _setup_approved_sc_with_active_po(app_config)
        gr = _create_gr(app_config, requester, po["po_id"], last_delivery="Y")
        assert gr["last_delivery"] == "Y"

    def test_create_gr_with_ld_conflict(self, app_config):
        admin, requester = _resolve_users(app_config)
        sc, po = _setup_approved_sc_with_active_po(app_config)
        _create_gr(app_config, requester, po["po_id"], last_delivery="Y")
        with pytest.raises(ConflictError, match="already marked as Last Delivery"):
            _create_gr(app_config, requester, po["po_id"], last_delivery="Y")

    def test_create_gr_with_ld_denied_excluded(self, app_config):
        """Denied GR with LD should not block new LD GR."""
        admin, requester = _resolve_users(app_config)
        sc, po = _setup_approved_sc_with_active_po(app_config)
        gr1 = _create_gr(app_config, requester, po["po_id"],
                         last_delivery="Y", status="pending")
        deny_gr(app_config, admin, gr1["gr_id"])
        gr2 = _create_gr(app_config, requester, po["po_id"], last_delivery="Y")
        assert gr2["last_delivery"] == "Y"

    def test_create_gr_invalid_last_delivery_value(self, app_config):
        admin, requester = _resolve_users(app_config)
        sc, po = _setup_approved_sc_with_active_po(app_config)
        data = {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 1000,
            "last_delivery": "yes",
        }
        with pytest.raises(ValidationError, match="must be 'Y' or 'N'"):
            create_gr(app_config, requester, data)

    def test_update_gr_set_ld_conflict(self, app_config):
        admin, requester = _resolve_users(app_config)
        sc, po = _setup_approved_sc_with_active_po(app_config)
        gr1 = _create_gr(app_config, requester, po["po_id"], last_delivery="Y")
        gr2 = _create_gr(app_config, requester, po["po_id"])
        with pytest.raises(ConflictError, match="already marked as Last Delivery"):
            update_gr(app_config, requester, gr2["gr_id"], {"last_delivery": "Y"})

    def test_update_gr_unset_ld_allowed(self, app_config):
        admin, requester = _resolve_users(app_config)
        sc, po = _setup_approved_sc_with_active_po(app_config)
        gr = _create_gr(app_config, requester, po["po_id"], last_delivery="Y")
        updated = update_gr(app_config, requester, gr["gr_id"], {"last_delivery": "N"})
        assert updated["last_delivery"] == "N"
```

- [ ] **Step 3: Add cascade flow tests**

```python
class TestLastDeliveryCascadeFinish:
    def test_finish_non_ld_gr_normal(self, app_config):
        admin, requester = _resolve_users(app_config)
        sc, po = _setup_approved_sc_with_active_po(app_config)
        gr = _create_gr(app_config, requester, po["po_id"])
        result = finish_gr(app_config, requester, gr["gr_id"])
        assert result["status"] == "finished"
        # PO should NOT be finished
        with connect(app_config) as conn:
            po_status = conn.execute(
                "SELECT status FROM pos WHERE po_id = ?", (po["po_id"],)
            ).fetchone()
            assert po_status["status"] == "active"

    def test_finish_ld_gr_needs_cascade(self, app_config):
        admin, requester = _resolve_users(app_config)
        sc, po = _setup_approved_sc_with_active_po(app_config)
        gr_ld = _create_gr(app_config, requester, po["po_id"], last_delivery="Y")
        gr_other = _create_gr(app_config, requester, po["po_id"])
        result = finish_gr(app_config, requester, gr_ld["gr_id"])
        assert result["needs_cascade"] is True
        assert gr_other["gr_id"] in result["grs_to_finish"]

    def test_finish_ld_gr_cascade_empty_needs_confirm(self, app_config):
        """LD GR with all others already finished — still needs confirmation."""
        admin, requester = _resolve_users(app_config)
        sc, po = _setup_approved_sc_with_active_po(app_config)
        gr_ld = _create_gr(app_config, requester, po["po_id"], last_delivery="Y")
        _create_finished_gr(app_config, admin, requester, po["po_id"])
        result = finish_gr(app_config, requester, gr_ld["gr_id"])
        assert result["needs_cascade"] is True
        assert result["grs_to_finish"] == []

    def test_finish_ld_gr_problematic_blocks(self, app_config):
        admin, requester = _resolve_users(app_config)
        sc, po = _setup_approved_sc_with_active_po(app_config)
        gr_ld = _create_gr(app_config, requester, po["po_id"], last_delivery="Y")
        gr_pending = _create_gr(app_config, requester, po["po_id"], status="pending")
        with pytest.raises(ConflictError) as exc:
            finish_gr(app_config, requester, gr_ld["gr_id"])
        assert exc.value.conflicts is not None
        conflict_ids = [c["gr_id"] for c in exc.value.conflicts]
        assert gr_pending["gr_id"] in conflict_ids

    def test_finish_ld_gr_denied_blocks(self, app_config):
        admin, requester = _resolve_users(app_config)
        sc, po = _setup_approved_sc_with_active_po(app_config)
        gr_ld = _create_gr(app_config, requester, po["po_id"], last_delivery="Y")
        _create_denied_gr(app_config, admin, requester, po["po_id"])
        with pytest.raises(ConflictError) as exc:
            finish_gr(app_config, requester, gr_ld["gr_id"])
        assert exc.value.conflicts is not None

    def test_finish_ld_gr_cascade_success(self, app_config):
        admin, requester = _resolve_users(app_config)
        sc, po = _setup_approved_sc_with_active_po(app_config)
        gr_ld = _create_gr(app_config, requester, po["po_id"], last_delivery="Y")
        gr_other = _create_gr(app_config, requester, po["po_id"])

        result = finish_gr(app_config, requester, gr_ld["gr_id"], confirm_cascade=True)
        assert result["gr"]["status"] == "finished"
        assert gr_other["gr_id"] in result["cascaded_grs"]
        assert result["po_finished"] == po["po_id"]

        # Verify all GRs and PO are finished
        with connect(app_config) as conn:
            for gr_id in [gr_ld["gr_id"], gr_other["gr_id"]]:
                status = conn.execute(
                    "SELECT status FROM gr_requests WHERE gr_id = ?", (gr_id,)
                ).fetchone()["status"]
                assert status == "finished"
            po_status = conn.execute(
                "SELECT status FROM pos WHERE po_id = ?", (po["po_id"],)
            ).fetchone()
            assert po_status["status"] == "finished"

    def test_confirm_cascade_on_non_ld_gr_ignored(self, app_config):
        """confirm_cascade=True on non-LD GR silently ignored, normal finish."""
        admin, requester = _resolve_users(app_config)
        sc, po = _setup_approved_sc_with_active_po(app_config)
        gr = _create_gr(app_config, requester, po["po_id"])
        result = finish_gr(app_config, requester, gr["gr_id"], confirm_cascade=True)
        assert result["status"] == "finished"
        assert "gr" not in result  # plain dict, not cascade wrapper

    def test_problematic_priority_over_approved(self, app_config):
        """When both problematic and approved GRs exist, problematic takes priority."""
        admin, requester = _resolve_users(app_config)
        sc, po = _setup_approved_sc_with_active_po(app_config)
        gr_ld = _create_gr(app_config, requester, po["po_id"], last_delivery="Y")
        _create_gr(app_config, requester, po["po_id"])  # approved
        _create_gr(app_config, requester, po["po_id"], status="pending")  # problematic

        with pytest.raises(ConflictError) as exc:
            finish_gr(app_config, requester, gr_ld["gr_id"])
        assert exc.value.conflicts is not None
```

Update the import at the top of `test_gr_service.py` to include `connect`:

```python
from sc_gr_app.db.connection import connect
```

(It may already be imported — check and add if missing.)

- [ ] **Step 4: Run tests**

```bash
cd tests && python -m pytest test_gr_service.py -v -k "TestLastDelivery"
```

Expected: 11 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_gr_service.py
git commit -m "test: add Last Delivery cascade and uniqueness unit tests"
```

---

### Task 12: Run full test suite and validate

**Files:** (verification only)

- [ ] **Step 1: Run all backend tests**

```bash
cd tests && python -m pytest -v
```

Resolve any test failures. Expected: all existing tests still pass + 11 new tests pass.

- [ ] **Step 2: Start dev server and verify frontend**

```bash
# Start backend (in one terminal)
python run.py

# Start frontend (in another terminal)
cd frontend && npm run dev
```

Manual test:
1. Create an approved SC with an active PO
2. Create two GRs — mark one as "Last Delivery (Y)"
3. Approve both GRs
4. Click "Finish" on the Last Delivery GR
5. Verify cascade confirmation dialog appears listing the other GR
6. Click "Confirm" → verify both GRs and PO are finished
7. Create another PO with two GRs, mark one as LD, finish the non-LD GR first, then finish the LD GR → verify dialog shows empty GR list, confirm finishes PO

- [ ] **Step 3: Commit any fixes if needed**

```bash
git add -A
git commit -m "chore: final adjustments after integration testing"
```
