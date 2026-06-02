# Workbench Redesign

**Date**: 2026-06-02
**Status**: approved

## Background

The workbench (HomeView) was refactored to a 3x3 grid layout (SC/PO/GR × Draft/Pending/Approved) with a dedicated `workbench_data` API endpoint. However, amount columns still remain, the PO row shows vendor instead of requester, GR row shows PO number instead of requester, and admin visibility rules don't differentiate between status columns.

## Requirements

1. Remove all amount display columns from the workbench
2. Show requester name (applicant) for all three entity rows
3. Requester: sees only own items across all 9 cells
4. Admin: Pending column shows everyone's SC/PO/GR; Approved and Draft columns show only own items
5. Each cell: display status, business number (SC NO / PO NO / GR ID), and requester name
6. Each cell: max 6 rows, "View all" links to list page
7. Row click navigates to detail page (GR rows should navigate to GR detail, not PO detail)

## What's Already Done

- 3×3 grid layout in `HomeView.vue`
- PO and GR draft status support (v9 migration, services, bridge)
- `workbench_data` bridge method returning per-status counts and rows
- `submit_po`, `submit_gr` bridge methods
- SC row already includes `requester_name`

## Changes

### Backend

#### 1. Add `requester_id` to PO table (migration v10)

- ALTER TABLE `pos` ADD COLUMN `requester_id` TEXT
- Backfill: `UPDATE pos SET requester_id = (SELECT sc.requester_id FROM sc_records sc WHERE sc.sc_id = pos.sc_id)`
- Update v9 table rebuild to include `requester_id` for fresh installs

#### 2. PO service: populate `requester_id`

- `create_po`: set `requester_id` from parent SC's `requester_id` by default
- `_generate_po_id` and all write paths: include `requester_id` in INSERT

#### 3. `workbench_data` query changes

- PO query: join `users` on `po.requester_id` (or via SC), return `requester_name` instead of `vendor_name`
- GR query: join `users` on `gr.requester_id`, return `requester_name` instead of `po_no`
- Remove amount columns from SELECT (sc_amount, po_amount, estimated_amount, con_value)
- PO query still returns `sc_id` for row-click navigation

#### 4. `workbench_data` admin visibility

Currently `_sc_visibility_clauses` for admin returns no restrictions (sees all). Modify `workbench_data` to apply per-status filtering:

- **Admin + Draft**: `sc.requester_id = ?` (own only)
- **Admin + Approved**: `sc.requester_id = ?` (own only)
- **Admin + Pending**: no requester filter (see all)
- **Requester + all cells**: `sc.requester_id = ?` (own only, unchanged)

Implementation: pass `own_only: bool` parameter per status query instead of relying solely on `_sc_visibility_clauses`.

### Frontend

#### 5. `HomeView.vue` template changes

- Remove `<span class="wb-cell__th-amt">` header from all three entity rows
- Remove `<span class="wb-cell__td-amt"><AmountDisplay ...></span>` from all three entity rows
- PO row: change `row.vendor_name` to `row.requester_name`
- GR row: change `row.po_no` to `row.requester_name`
- GR row: `@click` navigate to `/sc/${row.sc_id}/po/${row.po_id}/gr/${row.gr_id}` instead of `/sc/${row.sc_id}/po/${row.po_id}`

#### 6. `HomeView.vue` style changes

- Remove `.wb-cell__th-amt` and `.wb-cell__td-amt` CSS rules
- Adjust `.wb-cell__th-id` / `.wb-cell__td-id` flex to fill freed space
- Adjust `.wb-cell__th-sub` / `.wb-cell__td-sub` flex accordingly

#### 7. i18n updates

- Update `home.colPoNo` / `home.colGrId` usage if needed
- Ensure `home.colRequester` exists for all three rows

#### 8. Remove `AmountDisplay` import

- If `AmountDisplay` is no longer used in HomeView, remove the import

## Visibility Rules Summary

| Cell | Requester | Admin |
|------|-----------|-------|
| SC Draft | own only | own only |
| SC Pending | own only | **all** |
| SC Approved | own only | own only |
| PO Draft | own only | own only |
| PO Pending | own only | **all** |
| PO Approved | own only | own only |
| GR Draft | own only | own only |
| GR Pending | own only | **all** |
| GR Approved | own only | own only |

## Row Click Navigation

| Row | Target |
|-----|--------|
| SC | `/sc/:sc_id` |
| PO | `/sc/:sc_id/po/:po_id` |
| GR | `/sc/:sc_id/po/:po_id/gr/:gr_id` |

## Migration

- v10: `ALTER TABLE pos ADD COLUMN requester_id TEXT` + backfill from SC
- Update v9 rebuild DDL to include `requester_id` so fresh installs get the column

## Testing

- Unit: `workbench_data` returns correct visibility per role and status
- Unit: PO create populates `requester_id`
- Integration: requester sees only own data in all 9 cells
- Integration: admin sees own data in Approved/Draft, all data in Pending
- Manual: verify no amount columns rendered in workbench
- Manual: verify row click navigation (especially GR → GR detail)
