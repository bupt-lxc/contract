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
- `amount` only needs to be a valid number. It is not checked against PO amount, SC amount, GR amount, open amount, or remaining budget.
- Add an index on `po_id` for detail loading.

When a PO is deleted, related manual amount records must also be deleted. This can be implemented with explicit deletion inside `delete_po`, consistent with other PO child records.

## Permissions

Visibility follows PO detail visibility: anyone who can view the PO can view its manual annual amount records.

Mutation follows PO management permissions:

- Admin can add and delete records for any PO.
- The PO requester, or the owning SC requester when the PO belongs to an SC, can add and delete records for their PO.
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

Validation behavior:

- Missing PO raises not found.
- Invalid year raises validation error.
- Invalid type raises validation error.
- Non-numeric amount raises validation error.
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
      "created_at": "2026-07-09T..."
    }
  ]
}
```

For SC detail, each PO row can include the same `manual_amounts` array so the existing computed `po` object remains the source of truth in `PoDetailView`.

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

- `{previous_year} Provision` is filled from `po_manual_amounts` where `po_id = row.po_id`, `year = previous_year`, and `type = 'provision'`.
- `{selected_year} to be GR` is filled from `po_manual_amounts` where `po_id = row.po_id`, `year = selected_year`, and `type = 'to_be_gr'`.
- `{selected_year} FC GR` remains blank.
- `Remark` remains blank.

If a manual amount record does not exist, the export cell stays blank, not zero.

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
- Create accepts valid records and rejects invalid year/type/non-numeric amount.
- Duplicate `(po_id, year, type)` is rejected.
- Delete removes only the selected record.
- Non-authorized user cannot create or delete.
- `get_po_detail` and `get_sc_detail` return manual amounts.
- PO deletion removes related manual amounts.
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
