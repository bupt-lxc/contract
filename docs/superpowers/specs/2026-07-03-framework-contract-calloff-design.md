# Framework Contract Call-off Design

Date: 2026-07-03

## Summary

Extend the procurement system with a framework-contract (FC) layer that sits above the regular SC→PO→GR flow, enabling a 5-tier chain:

```
SC(FC) → PO(FC) → call-off SC (non-FC) → regular PO → GR
```

Each layer enforces that children's amounts do not exceed the parent's amount (budget cascade). SC(FC) and PO(FC) reuse the existing approval workflow. PO(FC) can only create call-off SCs, not GRs. Only POs under an FC-type SC can create call-off SCs.

---

## Data Model

Single new column on `sc_records`:

```sql
ALTER TABLE sc_records ADD COLUMN calloff_po_id TEXT REFERENCES pos(po_id);
```

- **NULL**: top-level SC (FC or regular, not created under any PO)
- **set**: call-off SC created under a PO(FC)

PO type is derived from its parent SC's `request_type` — no changes to `pos` table:

| Parent SC type | PO behavior | Can create |
|---|---|---|
| `FC` | FC PO | call-off SCs only |
| non-FC | Regular PO | GRs only |

SC type constraints:

| `sc_records.request_type` | `calloff_po_id` | Meaning |
|---|---|---|
| `FC` | NULL | Top-level framework contract |
| `material`/`service`/`fixed_asset` | NULL | Top-level regular SC (existing flow) |
| `material`/`service`/`fixed_asset` | set | Call-off SC under a PO(FC) |

Call-off SCs cannot have `request_type = 'FC'`, which combined with the rule that only FC SCs can spawn call-off-creating POs, limits nesting to exactly two SC levels.

---

## Budget Chain

```
SC(FC) amount
  └─ sum(PO(FC) amounts) ≤ SC(FC) amount         [existing: pos.sc_id → sc_records]
       └─ sum(call-off SC amounts) ≤ PO(FC) amount  [new: sc_records.calloff_po_id → pos]
            └─ sum(regular PO amounts) ≤ SC amount    [existing]
                 └─ sum(GR amounts) ≤ PO amount       [existing]
```

Validation points:

| Action | Check |
|---|---|
| Create/update PO(FC) | sibling POs + this PO ≤ parent SC(FC) amount (existing) |
| Create/submit/update call-off SC | sibling call-off SCs + this SC ≤ parent PO(FC) amount (new) |
| Edit SC(FC) amount down | blocked if > allocated PO amounts (existing) |
| Edit PO(FC) amount down | blocked if > sum of call-off SC amounts (new) |
| Edit call-off SC amount down | blocked if > allocated PO amounts (existing) |
| Edit PO amount down | blocked if > GR usage (existing) |

---

## Budget Display (all entity types)

SC and PO detail pages should show budget breakdown fields, parallel to what the PO detail already displays. The backend `budget_service` already computes most values; FC-type entities need new queries.

### Regular PO (unchanged from current)

| Field | Formula |
|---|---|
| PO Amount | `po_amount` |
| Open PO Amount | `po_amount - consumed - pending(excl)` |
| Consumed | `SUM(approved GR con_value)` |
| Pending (excl) | `SUM(pending/manager_confirm GR estimated_amount)` |
| Pending (incl) | `SUM(pending/manager_confirm GR gross_cost)` |

### PO(FC)

| Field | Formula |
|---|---|
| PO Amount | `po_amount` |
| Allocated Call-off SCs | `SUM(sc_amount) WHERE calloff_po_id = ?` (all statuses incl. draft) |
| 　Pending Call-off SCs | subset: `status IN ('manager_confirm', 'pending', 'approved')` |
| Open PO Amount | `po_amount - allocated_calloff` |
| Downstream Consumed | `SUM(approved GR con_value)` via call-off SCs → POs → GRs |
| Downstream Pending GR (excl) | `SUM(pending/manager_confirm GR estimated_amount)` same trace |
| Downstream Pending GR (incl) | `SUM(pending/manager_confirm GR gross_cost)` same trace |

### Regular SC / Call-off SC

| Field | Formula |
|---|---|
| SC Amount | `sc_amount` |
| Allocated to POs | `SUM(po_amount) WHERE sc_id = ?` |
| Unallocated | `sc_amount - allocated_po` |
| Consumed | `SUM(approved GR con_value)` via SC → POs → GRs |
| Pending GR (excl) | `SUM(pending/manager_confirm GR estimated_amount)` |
| Pending GR (incl) | `SUM(pending/manager_confirm GR gross_cost)` |

Call-off SCs additionally show parent context: linked PO(FC) ID, PO Amount, Open PO Amount.

### SC(FC)

| Field | Formula |
|---|---|
| SC Amount | `sc_amount` |
| Allocated to PO(FC)s | `SUM(po_amount) WHERE sc_id = ?` |
| Unallocated | `sc_amount - allocated_po` |
| Downstream Call-off SCs | `SUM(sc_amount)` traced SC(FC) → PO(FC)s → `sc_records.calloff_po_id` |
| 　Pending Call-off SCs | subset: `status IN ('manager_confirm', 'pending', 'approved')` |
| Downstream Consumed | `SUM(approved GR con_value)` full trace SC(FC) → PO(FC) → SC → PO → GR |
| Downstream Pending GR (excl) | `SUM(pending/manager_confirm GR estimated_amount)` |
| Downstream Pending GR (incl) | `SUM(pending/manager_confirm GR gross_cost)` |

### Frontend: SC Detail Card

Add a **Budget Summary** section below the existing `ScDetailCard` (or as additional rows within it), mirroring the PO detail budget display. Fields shown depend on entity type:

| Section | SC(FC) | SC/Call-off SC |
|---|---|---|
| SC Amount | ✓ | ✓ |
| Allocated to POs | ✓ | ✓ |
| Unallocated | ✓ | ✓ |
| Downstream Call-off SCs (pending) | ✓ | — |
| Consumed / Pending GR | ✓ | ✓ |

For call-off SCs: also show parent PO(FC) info with its Open PO Amount as context.

---

## Lifecycle Constraints

### Finish cascade (children must be final before parent can finish):

```
SC(FC) finish → requires all PO(FC)s finished
PO(FC) finish → requires all call-off SCs finished or denied
call-off SC finish → requires all regular POs finished (existing)
regular PO finish → requires all GRs in final state (existing)
```

### Creation gating:

| To create | Parent constraint |
|---|---|
| PO(FC) | SC(FC) approved |
| call-off SC | PO(FC) active |
| Regular PO under call-off SC | call-off SC draft or approved (existing rule) |
| GR | Parent PO's parent SC is non-FC |

### Recall rules:

| Action | Blocked if |
|---|---|
| Recall PO(FC) (active → draft) | any non-draft call-off SC exists under it |
| Recall call-off SC | any non-draft POs exist under it (existing) |

---

## API & Service Changes

### `sc_service.py`

- `create_sc` / `create_sc_draft`: accept optional `calloff_po_id`. When set:
  - Validate referenced PO exists, is `active`, and its parent SC has `request_type = 'FC'`
  - Validate `request_type != 'FC'` (call-off SCs cannot be FC)
  - Budget check: `sum(call-off SC amounts WHERE calloff_po_id = ?) + new_amount ≤ po_amount`
- `update_sc`: when updating `sc_amount` on a call-off SC, validate against PO(FC) remaining
- `submit_sc`: same budget check; for call-off SCs, validate parent PO(FC) is still active
- `finish_sc`: for FC-type SC, block if any child POs are not finished (existing logic covers this)
- `get_sc_detail`: for FC SCs, include child POs with their call-off SC counts and open amounts. For call-off SCs, include parent PO(FC) info.

### `po_service.py`

- `create_po`: when parent SC is FC type:
  - PO is automatically an FC PO (no GR creation)
  - PO status is `active` only if parent SC is approved
- `finish_po`: for FC PO:
  - Block if any call-off SC is not in final state (`finished` or `denied`)
  - Skip the GR final-state check (FC POs have no GRs)
- `update_po`: when updating `po_amount` downward on an FC PO:
  - Validate not below sum of call-off SC amounts
- `get_po_detail`: return call-off SC list for FC POs (instead of GR list)

### `gr_service.py`

- `create_gr`: reject if parent PO's parent SC has `request_type = 'FC'` (FC POs cannot have GRs)

### `budget_service.py`

New functions:

- `compute_po_fc_budget(po_id)`: FC PO budget — `{ po_amount, allocated_calloff_amount, pending_calloff_amount, open_po_amount, downstream_consumed, downstream_pending_gr, downstream_pending_gr_tax }`
- `compute_sc_fc_budget(sc_id)`: SC(FC) budget — full downstream trace through PO(FC)s → call-off SCs → POs → GRs
- `compute_sc_budget(sc_id)`: extend to include PO-allocated/unallocated breakdown (already has `allocated_po_amount`, `unallocated_sc_amount`)
- `compute_po_budget(po_id)`: unchanged for regular POs

---

## Frontend Changes

### PO type determines what's shown:

| Section | Regular PO | FC PO |
|---|---|---|
| PO info/header | ✓ | ✓ |
| GR Records list | ✓ | — |
| Create GR button | ✓ | — |
| Call-off SC list | — | ✓ |
| Create Call-off SC button | — | ✓ |

### SC List view

- "Create SC" button shows dropdown: **New SC** (top-level) / **New Call-off SC**
- Call-off SCs display a visual indicator (e.g., "Call-off" badge)
- "New Call-off SC" opens a PO(FC) selector showing available FC POs with their open amounts

### SC creation form

- When `calloff_po_id` is set: display linked PO(FC) info + remaining budget
- `request_type` picker excludes `FC` for call-off SCs
- Amount client-side validation: `sc_amount ≤ PO(FC) open amount`

### SC detail view

- Call-off SC: show parent PO(FC) link
- SC(FC): for each FC PO row, show call-off SC count and remaining open amount

### PO detail view (FC PO)

- Call-off SC list replaces GR list
- "Create Call-off SC" button opens SC creation form pre-filled with `calloff_po_id`
- Display remaining open amount

---

## Edge Cases

1. **`calloff_po_id` is immutable**: cannot transfer a call-off SC to a different PO(FC). Delete + recreate if needed.

2. **Vendor constraints**: existing `sc_vendors` junction + PO vendor validation covers FC POs as well — no special handling needed.

3. **Import/export**: `calloff_po_id` should be an exportable and importable field.

4. **Existing data**: treated as no existing FC data in production. Migration only adds the nullable column.

5. **SC(FC) approval cascade**: the existing `cascade_pos` on SC approve is unnecessary since draft POs can't be created under a non-approved SC. No action needed, but noted for potential cleanup.
