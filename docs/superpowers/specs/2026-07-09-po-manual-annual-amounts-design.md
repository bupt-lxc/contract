# PO Manual Annual Amounts Design

## Purpose

Requester users need a way to manually record annual PO amounts that are not part of the normal PO budget, GR, open amount, or validation calculations.

Two supported record types are required:

- `provision`: money that is actually spent in the following year but booked to the selected year. Example: `2024 provision` means the amount is spent in 2025 but recorded on 2024's account.
- `to_be_gr`: an estimate for how much will still be spent in the remaining time of the selected year. Example: `2025 to be GR` means the requester estimates that amount is still expected for 2025.

These records are informational only. They are shown on PO detail screens, visible when entering a PO from either the SC detail route or the independent PO detail route, and included in the PO annual report export.

## Data Model

Add a new table, not new columns on `pos`.

Table: `po_manual_amounts`

Columns:

- `manual_amount_id TEXT PRIMARY KEY`
- `po_id TEXT NOT NULL REFERENCES pos(po_id)`
- `year TEXT NOT NULL`
- `type TEXT NOT NULL CHECK (type IN ('provision', 'to_be_gr'))`
- `amount REAL NOT NULL`
- `created_by TEXT NOT NULL REFERENCES users(user_id)`
- `created_at TEXT NOT NULL`

Constraints and indexes:

- `UNIQUE(po_id, year, type)` prevents duplicate manual records for the same PO/year/type.
- `year` must be a four-digit string.
- `amount` only needs to be a valid number. Zero and negative values are allowed because the record is a manual bookkeeping entry, not a budget constraint. It is not checked against PO amount, SC amount, GR amount, open amount, or remaining budget.
- Add an index on `po_id` for detail loading.

Migration implementation:

- Bump `SCHEMA_VERSION` from 39 to 40.
- Add `_migrate_v40` to create `po_manual_amounts`.
- Wire v40 into `migrate()` immediately after v39.
- Update migration tests to expect the new schema version.

When a PO is deleted, related manual amount records must also be deleted before deleting the PO. When an SC is deleted and its child POs are deleted directly, related manual amount records for those child POs must also be deleted. Prefer explicit deletion in `delete_po` and `delete_sc`, consistent with current child-record cleanup patterns.

## Permissions

Visibility follows PO detail visibility: anyone who can view the PO can view its manual annual amount records.

Mutation uses a dedicated manual-amount permission, not the existing `can_manage_po` flag, because records may be added or deleted even when the PO is `finished`.

- Admin can add and delete records for any PO.
- The PO requester can add and delete records for their PO.
- The owning SC requester can add and delete records when the PO belongs to an SC.
- Finished POs still allow manual record add/delete.
- Other users cannot add or delete records.

Manual records are not sent through workflow, approval, notification, email, or operation-record side effects. They are intentionally simple user-entered records.

## Backend API

Add service functions in the PO domain:

- `list_po_manual_amounts(config, current_user, po_id) -> list[dict]`
- `create_po_manual_amount(config, current_user, po_id, data) -> dict`
- `delete_po_manual_amount(config, current_user, manual_amount_id) -> dict`

Bridge methods:

- `list_po_manual_amounts`
- `create_po_manual_amount`
- `delete_po_manual_amount`

List payload:

```json
{
  "po_id": "PO-..."
}
```

List response order:

- Sort by `year DESC`, then `type ASC`, then `created_at DESC`.

Create payload:

```json
{
  "po_id": "PO-...",
  "data": {
    "year": "2025",
    "type": "to_be_gr",
    "amount": 12345.67
  }
}
```

Delete payload:

```json
{
  "manual_amount_id": "PMA-..."
}
```

Delete response:

```json
{
  "deleted": true,
  "manual_amount_id": "PMA-..."
}
```

`manual_amount_id` generation:

- Use a compact generated text id with prefix `PMA-`.
- The id only needs to be unique and stable; it does not need to encode requester machine id or date.
- A UUID-style suffix is acceptable, for example `PMA-<uuidhex>`.

Validation behavior:

- Missing PO raises not found.
- Invalid year raises validation error.
- Invalid type raises validation error.
- Non-numeric amount raises validation error.
- Numeric `0` and negative amounts are accepted.
- Duplicate `(po_id, year, type)` raises `ConflictError` with a clear message.

## Detail Data Flow

The records must be available in both PO detail entry modes.

Independent PO detail route:

- `get_po_detail` returns a top-level `manual_amounts` array.

SC nested PO route:

- `get_sc_detail` attaches `manual_amounts` to each PO row in the returned `pos` array.

Recommended shape:

```json
{
  "po": { "...": "..." },
  "manual_amounts": [
    {
      "manual_amount_id": "PMA-...",
      "po_id": "PO-...",
      "year": "2025",
      "type": "to_be_gr",
      "amount": 12345.67,
      "created_by": "U...",
      "created_by_name": "Requester Name",
      "created_at": "2026-07-09T..."
    }
  ]
}
```

For SC detail, each PO row can include the same `manual_amounts` array so the existing computed `po` object remains the source of truth in `PoDetailView`.

Bridge timestamp formatting must include:

- top-level `manual_amounts` returned from `get_po_detail`
- nested `manual_amounts` attached to each `pos[]` row returned from `get_sc_detail`

## Frontend UI

Add one section to `PoDetailView` only.

Section name: `Manual Annual Amounts`

Table columns:

- Year
- Type
- Amount
- Created By
- Created At
- Actions

Actions:

- Add record button opens a small dialog.
- Delete action uses a confirmation prompt.
- Add/delete controls use a dedicated permission such as `can_manage_po_manual_amounts`, not `can_manage_po`.

Add dialog fields:

- Year text input, four-digit year.
- Type select with:
  - Provision
  - To be GR
- Amount numeric input.

The section appears on PO detail only. It is not shown in PO list, SC list, GR list, or dashboards.

## Annual Report Integration

PO annual report export uses manual amount records without changing the PO selection scope.

For each exported PO row:

- `{previous_year} Provision` is filled from `po_manual_amounts` where `po_id = internal PO id`, `year = previous_year`, and `type = 'provision'`.
- `{selected_year} to be GR` is filled from `po_manual_amounts` where `po_id = internal PO id`, `year = selected_year`, and `type = 'to_be_gr'`.
- `{selected_year} FC GR` remains blank.
- `Remark` remains blank.

If a manual amount record does not exist, the export cell stays blank, not zero.

The annual report query may select internal `po.po_id` for joining manual records, but the final exported row shape must not add a visible PO ID column.

SC-only annual report rows have no PO id, so these manual amount columns stay blank.

These records do not affect:

- `previous_year_gr`
- `selected_year_gr`
- PO open amount
- SC or PO budget cards
- GR approval or finish behavior
- any validation that compares PO, SC, or GR amounts

## Testing

Backend tests:

- Migration creates `po_manual_amounts`, unique constraint, and PO lookup index.
- Migration v40 is recorded and included in `SCHEMA_VERSION`.
- Create accepts positive, zero, and negative numeric amounts and rejects invalid year/type/non-numeric amount.
- Duplicate `(po_id, year, type)` is rejected.
- Delete removes only the selected record.
- Admin, PO requester, and owning SC requester can create/delete; non-authorized user cannot create/delete.
- `get_po_detail` and `get_sc_detail` return manual amounts.
- `get_po_detail` and `get_sc_detail` format manual amount timestamps through the bridge.
- PO deletion and SC deletion remove related manual amounts.
- PO annual report fills previous-year provision and selected-year to-be-GR for PO rows and leaves SC-only rows blank.

Frontend tests or build checks:

- `PoDetailView` renders manual records from both independent PO detail and SC nested detail data.
- Add/delete actions call the new bridge methods and refresh detail.
- Production build passes.

## Non-Goals

- No batch import/export of manual records.
- No edit operation after create; users can delete and recreate a record.
- No approval, notification, email, or workflow side effects.
- No budget or GR calculation changes.
- No display outside PO detail and PO annual report.
