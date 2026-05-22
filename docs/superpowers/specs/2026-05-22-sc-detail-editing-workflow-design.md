# SC Detail Editing Workflow Design

## Summary

The desktop app currently exposes search-oriented screens for SC, Vendor, PO, GR, Logs, and System. Users can inspect data, but they cannot create SC records, maintain PO/GR data, or perform status transitions from the UI. The existing right-side detail drawer also covers table columns, including status.

This design adds a dedicated SC Detail page as the single operational workspace for an SC and all of its PO and GR activity. List pages remain query-first. SC creation starts from the SC list. PO and GR creation/editing happen only inside SC Detail.

## Goals

- Keep list pages focused on search, filtering, and navigation.
- Add SC creation with `Save Draft` and `Submit` actions.
- Add a full SC Detail page reachable from SC, PO, and GR list pages.
- Support SC, PO, and GR editing and status transitions with clear permissions.
- Move status to the first table column and actions to the last table column.
- Remove the current drawer behavior for SC/PO/GR details so details do not cover table state.
- Preserve audit logging for every write and status transition.

## Non-Goals

- Vendor creation/editing from the UI.
- PO or GR creation directly from list pages.
- Reopening closed, denied, finished, approved, or cancelled records.
- Bulk edit, import, export, or shared-drive deployment changes.
- Role model changes beyond existing `admin` and `requester`.

## Chosen Approach

Use a dedicated SC Detail page.

SC, PO, and GR list rows navigate to the owning SC Detail page. SC Detail shows the complete SC record, all PO records under that SC, all GR records under those POs, and SC-related audit history. All PO and GR operations happen there.

This is preferred over extending the current drawer because the detail workflow is too dense for a narrow overlay, and the drawer currently obscures important table columns.

## Navigation And Page Structure

The main navigation remains:

- Home
- SC
- Vendor
- PO
- GR
- Logs
- System

List pages:

- First table column is always `Status`.
- Last table column is always `Actions`.
- `Actions` contains icon buttons.
- SC list has a `New SC` button.
- Vendor, PO, GR, and Logs remain query-only.
- SC row action opens that SC Detail.
- PO row action opens the owning SC Detail and highlights or scrolls to the PO.
- GR row action opens the owning SC Detail and highlights or scrolls to the GR.

SC Detail page:

- Header: back button, SC title, status badge, primary status actions.
- SC information section: full SC fields, view/edit modes.
- PO section: all PO records for the SC, with add/edit/status actions.
- GR section: all GR records under the SC's POs, with add/edit/status actions.
- Audit section: SC-related audit logs, read-only.

The existing drawer should not be used for SC/PO/GR full details. It may be removed or limited to lightweight read-only detail for Vendor/Logs.

## Permissions

Roles remain `requester` and `admin`.

Requester:

- Can create their own draft SC.
- Can edit their own draft SC.
- Can submit their own draft SC.
- Can view their own non-draft SC records.
- Cannot edit pending SC records.
- Cannot create or edit PO records.
- Cannot create or edit GR records.
- Cannot perform approval, denial, close, finish, or cancellation transitions.

Admin:

- Can view non-draft SC records.
- Cannot view any draft SC, including drafts created by other users.
- Can edit pending, approved, and denied SC records.
- Cannot edit closed SC records.
- Can approve, deny, and close SC records.
- Can create, edit, approve, and finish PO records.
- Can create, edit, approve, and cancel GR records.

Draft visibility:

- Draft SC records are visible only to the owner/requester.
- Draft SC records are not visible to admins.
- Detail APIs must enforce the same rule, so a draft cannot be accessed by ID by another user or by an admin.

## Status Model

SC statuses:

- `draft`
- `pending`
- `approved`
- `denied`
- `closed`

SC transitions:

- `draft -> pending` via `Submit`.
- `pending -> approved` via `Approve`.
- `pending -> denied` via `Deny`.
- `approved -> closed` via `Close`.

PO statuses:

- `po_pending`
- `po_approved`
- `finished`

PO transitions:

- `po_pending -> po_approved` via `Approve`.
- `po_approved -> finished` via `Finish`.

GR statuses:

- `pending`
- `approved`
- `cancelled`

GR transitions:

- `pending -> approved` via `Approve`.
- `pending -> cancelled` via `Cancel`.

No reopen or rollback transitions are included in the first version.

## SC Draft Rules

Draft creation is intentionally permissive.

Creating a draft requires:

- `requester_id`

Draft fields may be empty:

- `sc_no`
- `request_type`
- `cost_center`
- `sc_amount`
- `service_period_start`
- `service_period_end`
- `description`

Submitting a draft to pending requires:

- `request_type`
- `cost_center`
- `sc_amount > 0`
- `service_period_start`
- `service_period_end`
- `service_period_start <= service_period_end`

Submitting does not require `sc_no`.

Approving a pending SC requires:

- SC status is `pending`.
- `sc_no` is non-empty.

## Database Changes

The SQLite schema needs a migration because current SC fields are too strict for draft records.

SC table changes:

- Add `draft` to the `status` CHECK constraint.
- Allow these columns to be NULL:
  - `sc_no`
  - `request_type`
  - `cost_center`
  - `sc_amount`
  - `service_period_start`
  - `service_period_end`
  - `description`
- Keep these columns required:
  - `sc_id`
  - `requester_id`
  - `status`
  - `created_by`
  - `created_at`
  - `updated_at`

SQLite will likely require table rebuild migration:

1. Create a new `sc_records` table with the updated constraints.
2. Copy existing records.
3. Drop the old table.
4. Rename the new table.
5. Recreate indexes.
6. Record migration version.

Existing data remains valid.

## Backend Services

### SC Service

Add or update:

- `create_sc_draft(config, current_user, data)`
- `submit_sc(config, current_user, sc_id, data)`
- `update_sc(config, current_user, sc_id, data)`
- `approve_sc(config, current_user, sc_id)`
- `deny_sc(config, current_user, sc_id)`
- `close_sc(config, current_user, sc_id)`
- `get_sc_detail(config, current_user, sc_id)`

Rules:

- Requester can create only their own draft.
- Requester can edit only their own draft.
- Requester cannot edit pending SC.
- Admin can edit pending, approved, and denied SC.
- Closed SC is read-only.
- Admin cannot see draft SC.
- Approve requires `sc_no`.
- Updating SC amount must not reduce the amount below already allocated PO/GR usage.
- Every write and transition writes an audit log.

### PO Service

Add or update:

- `create_po(config, current_user, data)`
- `update_po(config, current_user, po_id, data)`
- `approve_po(config, current_user, po_id)`
- `finish_po(config, current_user, po_id)`

Rules:

- Admin only.
- PO can be created only under an approved SC.
- PO vendor must exist.
- PO amount must be positive.
- Total PO allocation must not exceed SC amount.
- Updating PO amount must not reduce below pending/approved GR usage.
- PO updates must not make total PO allocation exceed SC amount.
- `approve_po` requires status `po_pending`.
- `finish_po` requires status `po_approved`.
- Status transitions should use explicit methods, not direct status field edits in a generic form.
- Every write and transition writes an audit log.

### GR Service

Add or update:

- `create_gr(config, current_user, data)`
- `update_gr(config, current_user, gr_id, data)`
- `approve_gr(config, current_user, gr_id, con_value)`
- `cancel_gr(config, current_user, gr_id)`

Rules:

- Admin only.
- GR can be created only under `po_approved` PO.
- Parent SC must be `approved`.
- Parent SC must have `sc_no`.
- Parent PO must have `po_no`.
- Estimated amount must be positive.
- Pending and approved budget totals must not exceed SC or PO availability.
- Pending GR can be fully edited.
- Approved GR can edit `con_value` and `remark`, with budget recalculation.
- Cancelled GR is read-only.
- `approve_gr` requires status `pending`.
- `cancel_gr` requires status `pending`.
- Every write and transition writes an audit log.

## Query And Detail Visibility

SC list:

- Admin sees `pending`, `approved`, `denied`, and `closed`.
- Admin does not see `draft`.
- Requester sees their own `draft`.
- Requester sees non-draft SC records where they are the requester.

PO list:

- Does not return records under draft SC.
- Remains query-only.
- Row action opens owning SC Detail.

GR list:

- Does not return records under draft SC.
- Remains query-only.
- Row action opens owning SC Detail.

SC Detail:

- Must apply the same visibility rules as SC list.
- Must return:
  - SC record.
  - SC budget.
  - PO records with PO budget.
  - GR records.
  - SC audit logs.
  - Permission/action metadata for the current user.

## Bridge API

Add bridge methods:

- `get_sc_detail(payload)`
- `create_sc_draft(payload)`
- `submit_sc(payload)`
- `update_sc(payload)`
- `deny_sc(payload)`
- `close_sc(payload)`
- `create_po(payload)`
- `update_po(payload)`
- `approve_po(payload)`
- `finish_po(payload)`
- `create_gr(payload)`
- `update_gr(payload)`
- `approve_gr(payload)`
- `cancel_gr(payload)`

Existing methods remain:

- `current_user`
- `search_scs`
- `search_vendors`
- `search_pos`
- `search_grs`
- `search_audit_logs`
- `approve_sc` may be exposed if not already exposed.

All bridge methods:

- Validate payload is an object.
- Resolve current user from machine ID.
- Return `{ ok: true, data }` on success.
- Return `{ ok: false, error }` on failure.
- Do not leak unhandled exceptions to the UI.

## Frontend Behavior

### Lists

Update table definitions so status is first and actions are last.

SC list:

- Adds `New SC`.
- Row/action opens SC Detail.
- Does not use the drawer for SC details.

PO list:

- Query-only.
- Row/action opens owning SC Detail with the PO highlighted.

GR list:

- Query-only.
- Row/action opens owning SC Detail with the GR highlighted.

### New SC

The New SC form supports:

- Save Draft
- Submit

Save Draft:

- Requires only owner/requester context.
- Creates a draft SC.
- Opens the created SC Detail.

Submit:

- Validates required submission fields.
- Creates or updates the SC as pending.
- Opens SC Detail after success.

### SC Detail

The detail page should show action buttons based on server-provided permissions and current status.

SC actions:

- Edit
- Submit
- Approve
- Deny
- Close

PO actions:

- Add PO
- Edit PO
- Approve PO
- Finish PO

GR actions:

- Add GR
- Edit GR
- Approve GR
- Cancel GR

Dangerous or final transitions require confirmation:

- Deny SC
- Close SC
- Finish PO
- Cancel GR

Errors:

- Show backend error messages near the form or action area.
- Keep the user on the current page.
- Refresh detail after successful writes.

## UI Layout Notes

- Avoid nested cards.
- Use full-width page sections for SC, PO, GR, and Audit.
- Use compact tables for PO and GR.
- Use stable action icon column widths so text does not shift the table.
- Keep the status badge column visible and first.
- Do not use the right-side drawer for the main SC/PO/GR workflow.

## Testing

### Backend Service Tests

Cover:

- Draft creation allows empty business fields.
- Submit validates business fields and allows empty `sc_no`.
- Approve fails when `sc_no` is missing.
- Owner cannot edit pending SC.
- Admin cannot see draft SC.
- Requester cannot see another requester's draft SC.
- Admin can edit pending, approved, and denied SC.
- Closed SC cannot be edited.
- PO create/update budget validation.
- PO approve/finish transitions.
- GR create/update budget validation.
- GR approve/cancel transitions.
- Every write action creates an audit log.

### Bridge Tests

Cover:

- New bridge methods wrap success responses.
- New bridge methods wrap service errors.
- Non-object payloads are rejected.
- Unauthorized users cannot write.
- Requester/admin permission branches are enforced.

### Frontend Tests

Cover:

- Status column first and Actions column last.
- SC New form sends correct Save Draft payload.
- SC New form sends correct Submit payload.
- PO list action navigates to SC Detail with PO target.
- GR list action navigates to SC Detail with GR target.
- Detail action visibility follows permission metadata.
- System/detail auth state does not rely on stale cached authorization.

### Manual Acceptance

- Requester creates a draft SC and sees it.
- Admin does not see that draft SC.
- Another requester does not see that draft SC.
- Requester submits draft without `sc_no`; SC becomes pending.
- Requester cannot edit the pending SC.
- Admin sees the pending SC.
- Admin cannot approve pending SC until `sc_no` is filled.
- Admin fills `sc_no` and approves the SC.
- Admin creates and edits PO records in SC Detail.
- Admin approves and finishes a PO.
- Admin creates and edits GR records in SC Detail.
- Admin approves and cancels GR records.
- PO and GR list actions open the correct SC Detail and focus the target record.
- The detail workflow no longer covers status columns in list pages.
