# Last Delivery GR — auto-finish PO cascade

## Summary

When a GR marked as "Last Delivery" (`last_delivery = 'Y'`) is finished, the system
automatically cascades: finish all other approved GRs under the same PO, then finish the PO
itself — all in a single transaction. Also enforces that only one active GR per PO can be
marked as Last Delivery.

---

## 1. Last Delivery uniqueness constraint

### Create GR

In `gr_service.create_gr`, before inserting the GR:

- If `last_delivery = 'Y'`, query for any other GR under the same PO with `last_delivery = 'Y'`
  and `status NOT IN ('denied', 'finished')`.
- If found → `ConflictError("GR {gr_id} under this PO is already marked as Last Delivery")`

### Edit GR

In `gr_service.update_gr`, when `last_delivery` is being set to `'Y'`:

- Same check, excluding the current GR (`gr_id != ?`).
- If found → same error.

### Rationale

Denied and finished GRs are excluded from the check: denied GRs are already blocked from
being finished (user must handle them), and finished GRs under a finished PO will never
coexist with new GRs since a finished PO blocks GR creation entirely.

---

## 2. `finish_gr` — Last Delivery cascade logic

### New parameter

`finish_gr(config, current_user, gr_id, force_cascade=False)`

### New exception

`LastDeliveryCascadeNeeded(gr_ids: list[str])` in `sc_gr_app/errors.py`.
Raised when cascade is needed but `force_cascade` is not set.
The API bridge catches this and returns `{ok: false, needs_cascade: true, grs_to_finish: [...]}`.

### Flow

```
finish_gr(gr_id, force_cascade=False)
  |
  +-- GR not approved → ConflictError (existing check)
  |
  +-- last_delivery != 'Y' → normal finish (existing behavior, unchanged)
  |
  +-- last_delivery == 'Y'
       |
       +-- Query all other GRs under same PO, categorize:
       |     problematic   = status IN ('draft', 'manager_confirm', 'pending')
       |     approved_nf   = status = 'approved' (need auto-finish)
       |     already_final  = status IN ('finished', 'denied') → ignored
       |
       +-- problematic non-empty → ConflictError:
       |     "以下 GR 必须先处理：GR-xxx(pending), GR-yyy(draft)"
       |
       +-- force_cascade=False
       |     → raise LastDeliveryCascadeNeeded(approved_nf_gr_ids)
       |     (list may be empty — means just "finish GR + PO" with no GRs to cascade)
       |
       +-- force_cascade=True
            → single transaction:
              1. Finish all approved_nf GRs (update status='finished', set finished_by/at)
              2. Write operation_record for each
              3. Finish THIS GR (status='finished')
              4. Call _finish_po_in_transaction(conn, po_id, ...) to finish PO
              5. Queue notifications for all finished GRs + PO
              6. COMMIT
```

### `_finish_po_in_transaction` helper

Extracted from `po_service.finish_po` — takes a connection and operates within an existing
transaction. Does the PO status update + operation record + notification. Both `finish_po`
(after its own checks + lock) and `finish_gr` (during Last Delivery cascade) call this helper.

The existing `finish_po` retains its own lock acquisition, SC status check, and GR/FC
final-state validations, then delegates to `_finish_po_in_transaction`.

---

## 3. API Bridge changes

`bridge.py` `finish_gr`:

- Accepts optional `force_cascade` from payload (default `False`)
- Passes it through to `gr_service.finish_gr`
- Catches `LastDeliveryCascadeNeeded` → returns:
  ```json
  {"ok": false, "needs_cascade": true, "grs_to_finish": ["GR-xxx", "GR-yyy"]}
  ```

---

## 4. Frontend changes

### `useGr.js`

`finishGr(grId, forceCascade = false)` — passes `force_cascade` in payload.

### `GrDetailView.vue` — `handleFinish`

### `PoDetailView.vue` — `handleGrFinish`

Both follow the same pattern:

```
1. Confirm dialog: "确定要完成此 GR 吗？"
2. Call finishGr(grId, false)
3. If ok → success message, refresh
4. If needs_cascade → show cascade confirmation dialog:
     a) GRs to cascade non-empty:
        "此 GR 为最后交付，以下 GR 将被一并完成：
         • GR-xxx
         • GR-yyy
         完成后 PO 也将自动完成。是否继续？"
     b) GRs to cascade empty (all others already final):
        "此 GR 为最后交付。完成后 PO 也将自动完成。是否继续？"
     [取消] [确认]
5. On confirm → call finishGr(grId, true)
6. If ok → "GR 已完成，PO 已自动完成", refresh
7. On error → show error message
```

### i18n keys (zh-CN / en-US)

| Key | zh-CN | en-US |
|-----|-------|-------|
| `gr.lastDeliveryCascadeTitle` | 最后交付确认 | Last Delivery Confirmation |
| `gr.lastDeliveryCascadeMessage` | 此 GR 为最后交付，以下 GR 将被一并完成：\n{list}\n\n完成后 PO 也将自动完成。是否继续？ | This GR is the last delivery. The following GRs will also be finished:\n{list}\n\nThe PO will be finished afterwards. Continue? |
| `gr.lastDeliveryNoCascadeMessage` | 此 GR 为最后交付。完成后 PO 也将自动完成。是否继续？ | This GR is the last delivery. The PO will be finished afterwards. Continue? |
| `gr.grAndPoFinished` | GR 已完成，PO 已自动完成 | GR finished, PO auto-finished |

---

## 5. Testing

### Unit tests (`test_gr_service.py`)

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Create GR with `last_delivery=Y`, no other LD GR | Success |
| 2 | Create GR with `last_delivery=Y`, active LD GR exists | ConflictError |
| 3 | Update GR to set `last_delivery=Y`, active LD GR exists | ConflictError |
| 4 | Finish non-LD GR | Normal finish (existing behavior) |
| 5 | Finish LD GR, all other GRs finished, `force_cascade=False` | LastDeliveryCascadeNeeded with empty list |
| 6 | Finish LD GR, has approved GRs, `force_cascade=False` | LastDeliveryCascadeNeeded raised |
| 7 | Finish LD GR, has problematic GRs (draft/pending) | ConflictError with list |
| 8 | Finish LD GR, has denied GRs | ConflictError with list |
| 9 | Finish LD GR, `force_cascade=True` | All approved GRs + this GR + PO finished in one tx |
| 10 | Cascade with concurrent state change | Transaction rolls back |

### Integration tests

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Full UI flow: finish LD GR with cascade | Dialog → confirm → all finished → PO finished |
| 2 | UI flow: cancel cascade dialog | No changes |
| 3 | UI flow: error from backend shown correctly | Error message displayed |

---

## 6. Edge cases

- **FC PO**: FC POs use call-off SCs, not GRs. Last Delivery logic does not apply. GR creation
  under FC POs is already blocked (`Cannot create GR under an FC PO`).
- **Already finished PO**: If PO is somehow finished between the confirmation dialog and the
  cascade call, the transaction will fail because `_finish_po_in_transaction` checks PO status.
- **Concurrent finish of another GR**: Protected by the `sc:{sc_id}` lease lock acquired at the
  start of `finish_gr` — no other GR operations under this SC can proceed concurrently.
