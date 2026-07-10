# Last Delivery GR — auto-finish PO cascade

## Summary

When a GR marked as "Last Delivery" (`last_delivery = 'Y'`) is finished, the system
automatically cascades: finish all other approved GRs under the same PO, then finish the PO
itself — all in a single transaction. Also enforces that only one active GR per PO can be
marked as Last Delivery.

---

## 1. `last_delivery` field validation

Accepted values: `'Y'`, `'N'`, `NULL` / `None` / `''`. Any other value is rejected with
`ValidationError("last_delivery must be 'Y' or 'N'")`.

Applied in both `create_gr` and `update_gr` whenever the field is present in the payload.

---

## 2. Last Delivery uniqueness constraint

### Create GR

In `gr_service.create_gr`, before inserting:

- If `last_delivery = 'Y'`, query for any other GR under the same PO with `last_delivery = 'Y'`
  and `status NOT IN ('denied', 'finished')`.
- If found → `ConflictError("GR {gr_id} under this PO is already marked as Last Delivery")`

### Edit GR

In `gr_service.update_gr`, when `last_delivery` is being set to `'Y'`:

- Same check, excluding the current GR (`gr_id != ?`).
- If found → same error.

Unsetting `last_delivery` from `'Y'` to `'N'` or `NULL` is allowed whenever the GR is in an
editable status (draft, manager_confirm, pending, approved). No additional constraint applies.

### Design rationale

- Finished GRs excluded: a finished PO blocks GR creation, so finished LD GRs cannot coexist
  with new GRs.
- Denied GRs excluded: a denied GR cannot be finished, so it cannot trigger the cascade.
  Excluding it from the uniqueness check allows another GR to take over the LD role.
- Draft GRs ARE included: two draft GRs under the same PO cannot both claim LD. This prevents
  confusion when they are later submitted.

---

## 3. `finish_gr` — Last Delivery cascade logic

### Signature

`finish_gr(config, current_user, gr_id, confirm_cascade=False)`

### New exception

`LastDeliveryCascadeNeeded(gr_ids: list[str])` in `sc_gr_app/errors.py`.
Raised when a Last Delivery GR is being finished without `confirm_cascade` and no problematic
GRs block the operation.

The API bridge catches it and returns:
```json
{"ok": false, "needs_cascade": true, "grs_to_finish": ["GR-xxx", "GR-yyy"]}
```

### Flow

```
finish_gr(gr_id, confirm_cascade=False)
  |
  +-- GR not approved → ConflictError (existing check)
  |
  +-- last_delivery != 'Y' → normal finish (existing behavior; confirm_cascade ignored)
  |
  +-- last_delivery == 'Y'
       |
       +-- Query all other GRs under same PO, categorize:
       |     problematic   = status IN ('draft', 'manager_confirm', 'pending', 'denied')
       |     approved_nf   = status = 'approved' (will be auto-finished on cascade)
       |     already_final  = status = 'finished' → silently ignored
       |
       +-- problematic non-empty → ConflictError with structured conflicts list:
       |     {"conflicts": [{"gr_id": "GR-xxx", "status": "pending"},
       |                     {"gr_id": "GR-yyy", "status": "draft"}]}
       |     (problematic takes priority: if both problematic AND approved_nf exist,
       |      only the ConflictError is raised — user must resolve problematic GRs first)
       |
       +-- confirm_cascade=False
       |     → raise LastDeliveryCascadeNeeded(approved_nf_gr_ids)
       |     (list may be empty — means just "finish GR + PO" with no GRs to cascade)
       |
       +-- confirm_cascade=True
            → single transaction (BEGIN IMMEDIATE … COMMIT):
              1. Re-query and re-validate all other GRs against the same categorization.
                 If any GR's status changed (e.g. approved→denied) since the initial check:
                 → ConflictError with the updated conflicts list, transaction rolls back.
              2. For each GR in approved_nf:
                 a. UPDATE status='finished', finished_by=current_user, finished_at=<shared_ts>,
                    updated_at=<shared_ts>
                 b. write_operation_record(action_type="finish_gr", object_type="gr", ...)
                 c. NO notification queued for cascaded GRs (only primary GR + PO get emails)
              3. Finish THIS GR (the primary LD GR):
                 a. UPDATE status='finished', finished_by=current_user, finished_at=<shared_ts>,
                    updated_at=<shared_ts>
                 b. write_operation_record(action_type="finish_gr", ...)
                 c. Queue notification for this GR (transition "finish")
              4. Call _finish_po_in_transaction(conn, po_id, current_user, shared_ts) → see §4
              5. COMMIT
```

All cascade-finished GRs share the same `finished_at` timestamp (`shared_ts`), computed once at
the start of the transaction. This makes the batch auditable as a single operation.

### Return value on success

```json
{
  "ok": true,
  "data": { /* primary GR dict */ },
  "cascaded_grs": ["GR-xxx", "GR-yyy"],
  "po_finished": "PO-abc"
}
```

---

## 4. `_finish_po_in_transaction` helper

Extracted from `po_service.finish_po`. Operates within an existing connection + transaction.
MUST NOT acquire any locks.

### Signature

```python
def _finish_po_in_transaction(conn, po_id: str, current_user: dict, timestamp: str) -> dict:
```

### Contract

1. Validate PO is in `active` status → if not, raise `ConflictError("PO must be active")`
2. Validate parent SC is not `finished` → if finished, raise `ConflictError("Finished SC cannot be edited")`
3. UPDATE pos SET status='finished', finished_by=current_user, finished_at=timestamp,
   updated_at=timestamp WHERE po_id=?
4. write_operation_record(action_type="finish_po", object_type="po", ...)
5. Queue notification for PO (transition "finish")
6. Return the updated PO dict

The existing `finish_po` public function retains its own lock acquisition, SC/GR/FC pre-checks,
then delegates to `_finish_po_in_transaction` for the actual update.

### Schema: add `finished_by` to `pos`

New migration: `ALTER TABLE pos ADD COLUMN finished_by TEXT REFERENCES users(user_id)`.

This column is set by both the manual `finish_po` path and the cascade path. The existing
`finish_po` currently only sets `finished_at` — this is updated to also set `finished_by`.

---

## 5. API Bridge changes

`bridge.py` `finish_gr`:

- Accepts optional `confirm_cascade` from payload (default `False`)
- Passes it through to `gr_service.finish_gr`
- Catches `LastDeliveryCascadeNeeded` → returns structured `needs_cascade` response
- On cascade success: calls `_auto_open_outlook_draft("gr", gr_id, "finish")` for primary GR only,
  and `_auto_open_outlook_draft("po", po_id, "finish")` for the auto-finished PO
- Cascaded GRs do NOT trigger `_auto_open_outlook_draft` (consistent with notification strategy)

---

## 6. Notification strategy

| Entity | Notification sent? | Transition |
|--------|-------------------|------------|
| Primary LD GR (user clicked Finish) | Yes | `finish` |
| Cascaded GRs (auto-finished) | No | — |
| Auto-finished PO | Yes | `finish` |

Rationale: sending per-GR emails for cascaded GRs would be noisy. The primary GR notification
and PO notification together provide a complete audit picture. Operation records are still
written for every entity.

---

## 7. Frontend changes

### `useGr.js`

`finishGr(grId, confirmCascade = false)` — passes `confirm_cascade` in payload.

### `GrDetailView.vue` — `handleFinish`

### `PoDetailView.vue` — `handleGrFinish`

Both follow the same pattern:

```
1. Confirm dialog: "确定要完成此 GR 吗？"
2. Call finishGr(grId, false)
3. If ok → success message, refresh
4. If needs_cascade → show cascade confirmation dialog:
     a) grs_to_finish non-empty:
        "此 GR 为最后交付，以下 GR 将被一并完成：
         • GR-xxx
         • GR-yyy
         完成后 PO 也将自动完成。是否继续？"
     b) grs_to_finish empty (all others already finished):
        "此 GR 为最后交付。完成后 PO 也将自动完成。是否继续？"
     [取消] [确认]
5. On confirm → call finishGr(grId, true)
6. If ok → "GR 已完成，PO 已自动完成", refresh
7. On error → show error message
```

No ordering is enforced: non-LD GRs can be individually finished before the LD GR. The LD
designation serves as a convenience trigger, not a sequencing constraint.

### i18n keys (zh-CN / en-US)

| Key | zh-CN | en-US |
|-----|-------|-------|
| `gr.lastDeliveryCascadeTitle` | 最后交付确认 | Last Delivery Confirmation |
| `gr.lastDeliveryCascadeMessage` | 此 GR 为最后交付，以下 GR 将被一并完成：\n{list}\n\n完成后 PO 也将自动完成。是否继续？ | This GR is the last delivery. The following GRs will also be finished:\n{list}\n\nThe PO will be finished afterwards. Continue? |
| `gr.lastDeliveryNoCascadeMessage` | 此 GR 为最后交付。完成后 PO 也将自动完成。是否继续？ | This GR is the last delivery. The PO will be finished afterwards. Continue? |
| `gr.grAndPoFinished` | GR 已完成，PO 已自动完成 | GR finished, PO auto-finished |

---

## 8. Import service fix

`import_service.py` line 635 has a pre-existing bug: `parse_date(row.get("last_delivery"))`
treats the `last_delivery` field (a `'Y'`/`'N'` flag) as a date, silently dropping the value.

Fix: change to `row.get("last_delivery")` (direct string passthrough).

Without this fix, imported GRs with `last_delivery='Y'` will never trigger the cascade.

---

## 9. Testing

### Unit tests (`test_gr_service.py`)

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Create GR with `last_delivery=Y`, no other LD GR | Success |
| 2 | Create GR with `last_delivery=Y`, active LD GR exists | ConflictError |
| 3 | Create GR with `last_delivery=Y`, denied LD GR exists | Success (denied excluded from check) |
| 4 | Create GR with `last_delivery="yes"` (invalid value) | ValidationError |
| 5 | Update GR to set `last_delivery=Y`, active LD GR exists | ConflictError |
| 6 | Update GR to unset `last_delivery` (Y→N) | Success |
| 7 | Finish non-LD GR | Normal finish (existing behavior) |
| 8 | Finish LD GR, all other GRs finished, `confirm_cascade=False` | LastDeliveryCascadeNeeded with empty list |
| 9 | Finish LD GR, has approved GRs, `confirm_cascade=False` | LastDeliveryCascadeNeeded with list |
| 10 | Finish LD GR, has problematic GRs (draft/pending/denied) | ConflictError with structured conflicts |
| 11 | Finish LD GR, has BOTH approved AND problematic GRs | ConflictError (problematic takes priority) |
| 12 | Finish LD GR, `confirm_cascade=True` | All approved GRs + this GR + PO finished in one tx |
| 13 | Cascade: approved GR status changed to denied between calls | Transaction rolls back, ConflictError |
| 14 | Confirm cascade on non-LD GR with `confirm_cascade=True` | Normal finish (parameter silently ignored) |

### Integration tests

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Full UI flow: finish LD GR with cascade | Dialog → confirm → all finished → PO finished |
| 2 | UI flow: cancel cascade dialog | No changes |
| 3 | UI flow: problematic GR error from backend | Error displayed with GR list |

---

## 10. Edge cases

- **FC PO**: FC POs use call-off SCs, not GRs. Last Delivery logic does not apply. GR creation
  under FC POs is already blocked (`Cannot create GR under an FC PO`).

- **Lock re-entrancy**: `_finish_po_in_transaction` MUST NOT acquire the `sc:{sc_id}` lock.
  The caller (`finish_gr`) already holds it. Acquiring it again would deadlock.

- **Already finished PO**: `_finish_po_in_transaction` validates PO is `active` before updating.
  If the PO was finished between the confirmation dialog and the cascade call, the transaction
  fails with `ConflictError("PO must be active")`.

- **SC finished mid-operation**: `_finish_po_in_transaction` validates SC is not finished.
  If the SC was finished between calls, the transaction fails.

- **Concurrent GR state changes**: The cascade re-queries and re-validates all GRs inside the
  transaction. Any status change since the initial check is detected and causes a rollback with
  `ConflictError`. The `sc:{sc_id}` lock prevents most concurrent changes, but the re-check is
  a safety net for the time gap between the `needs_cascade` response and the `confirm_cascade`
  retry (the lock is released and re-acquired across these two calls).

- **Draft GR as LD**: Allowed. The uniqueness constraint applies to draft GRs (two draft GRs
  cannot both claim LD). If a draft LD GR is submitted and later denied, another GR can take
  over the LD role.

- **No ordering enforcement**: Non-LD GRs can be individually finished before the LD GR.
  The LD designation is a convenience trigger, not a sequencing requirement.

- **Budget**: No budget re-checks are needed during cascade — all GRs being finished are already
  approved, so their amounts are already committed. Finished GRs drop out of budget calculations
  (which consider only pending/manager_confirm/approved statuses). The frontend should filter
  finished POs from budget displays to avoid showing misleading `open_po_amount` values.
