# SC Multiple Assignees — Design Spec

**Date**: 2026-07-08
**Scope**: Allow multiple users to view and receive notifications for a single SC, while the primary `requester_id` retains full operational control.

## Motivation

Currently each SC has exactly one `requester_id`. In practice multiple people may share responsibility for an SC and need to see it in their workbench and receive status-change notifications.

## Design Decision

**Approach A: primary requester + view-only assignees** — smallest change, lowest risk.

- `requester_id` remains the single owner with full edit/submit/approve permissions.
- A new junction table `sc_assignees` stores additional users who can **view** the SC and receive **notifications**.
- Assignees have no edit, submit, approve, or delete rights.

## Schema Change (v37 migration)

```sql
CREATE TABLE sc_assignees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sc_id TEXT NOT NULL REFERENCES sc_records(sc_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    UNIQUE(sc_id, user_id)
);
CREATE INDEX idx_sc_assignees_sc ON sc_assignees(sc_id);
CREATE INDEX idx_sc_assignees_user ON sc_assignees(user_id);
```

The primary requester is NOT automatically stored in `sc_assignees` — they already own the SC via `sc_records.requester_id`.

## Backend Changes

### sc_service.py

| Function | Change |
|---|---|
| `_assert_can_view_sc` | Also allow if user_id is in `sc_assignees` for this SC |
| `_sc_permissions` | No change. Assignees naturally get `false` for all operational permissions (`can_edit_sc`, `can_submit_sc`, etc.) because `is_owner = user.user_id == sc.requester_id` is false for them. No need to add a `can_view` key — view is gated by `_assert_can_view_sc`, not `_sc_permissions`. |
| `create_sc_draft` | Accept `assignee_ids` in data, call `_sync_sc_assignees` after insert |
| `update_sc` | Accept `assignee_ids` in data, call `_sync_sc_assignees`. Add `"assignee_ids"` to `OPTIONAL_UPDATE_FIELDS` tuple. |
| `submit_sc` | Accept `assignee_ids` in merged data, call `_sync_sc_assignees` (same pattern as `_sync_sc_vendors`) |
| `create_sc` (direct submit) | No change. `assignee_ids` in data is silently ignored — the INSERT only picks named columns. This is intentional: direct submit path does not support assignees. |
| `_sync_sc_assignees(conn, sc_id, assignee_ids)` | New helper — DELETE all existing rows for this sc_id, INSERT new list from `assignee_ids`. Same pattern as `_sync_sc_vendors`. |
| `get_sc_detail` | Return `assignees` list (user_id, user_name from users table by joining `sc_assignees`) |
| `transfer_sc` | No change — only primary requester is transferred. Assignees stay with the SC. |
| `delete_sc` | Add explicit `DELETE FROM sc_assignees WHERE sc_id = ?` before deleting from `sc_records`, matching the `sc_vendors` pattern. |
| `recall_sc` | Permission unchanged (only requester can recall). Notification will CC assignees as a natural consequence of the notification update — desired behavior. |

### query_service.py

**Single point of change: `_sc_visibility_clauses`.** Update this one function to include the `sc_assignees` subquery. This automatically fixes all four call sites:

- `search_scs`
- `search_pos` — assignees will see POs under their assigned SCs
- `search_grs` — assignees will see GRs under their assigned SCs
- `workbench_data` — must be refactored to call `_sc_visibility_clauses` instead of its current hardcoded `sc.requester_id = ?` checks (at lines ~693, ~718, ~760 for SC/PO/GR status columns respectively)

Change from:
```
sc.requester_id = ?
```
to:
```
(sc.requester_id = ? OR sc.sc_id IN (SELECT sc_id FROM sc_assignees WHERE user_id = ?))
```

### notification_service.py

**Mechanism: inline query in `queue_status_change`.** When `entity_type == 'sc'`, after resolving existing CC recipients, also query:
```sql
SELECT user_id FROM sc_assignees WHERE sc_id = ?
```
and merge those IDs into the CC list. This is simpler than writing assignee IDs into `notification_config.cc_user_ids` on every create/update/submit, and keeps notification config as a separate concern.

The primary requester remains the To recipient; assignees are added as CC.

Recall notifications also CC assignees — desired behavior since assignees should know about status changes.

### API bridge (bridge.py)

- `create_sc_draft`, `update_sc`, `submit_sc`: extract `assignee_ids` from payload data (already passed through, same as `vendor_ids`)
- `get_sc_detail`: return assignees in response
- **`open_entity_email`**: for SC entities, also query `sc_assignees` and merge into CC list, consistent with `queue_status_change`
- New endpoint: none needed

## Frontend Changes

### ScFormDialog.vue

- Add `<el-select multiple>` for assignee selection below the requester dropdown
- Label: "协作者" / "Assignees"
- Data binding: `form.assignee_ids` (initialized as `[]`)
- **Exclude requester**: filter user options with `users.filter(u => u.user_id !== form.requester_id)`, or use `:disabled` on the currently selected requester's option. Re-filter when requester changes.
- **Edit mode**: populate `form.assignee_ids` from `props.record.assignees` (requires `ScDetailView.vue` to pass assignees in the record prop — see below)

### ScDetailView.vue

- When opening edit dialog, pass `assignees` in the record prop:
  ```
  { ...detail.sc, vendors: detail.vendors, assignees: detail.assignees }
  ```
- **Transfer dialog**: add a note "协作者将保持不变" / "Assignees will remain unchanged" below the user selector (minor UX improvement)

### ScDetailCard.vue

- Show assignee list below requester field
- Format: comma-separated user names

### ScTable.vue

- No required change (requester_name column stays as the primary owner)

## What Does NOT Change

- `create_sc` (direct submit flow) — assignee_ids silently ignored
- `approve_sc`, `deny_sc`, `finish_sc`, `confirm_sc` — permission checks unchanged
- Import/export templates and logic
- `transfer_sc` — only primary requester is transferred; assignees persist
- All existing `requester_id`-based permission checks for write operations

## Edge Cases

1. **Primary requester also listed as assignee**: UI prevents it by filtering out the requester from the assignee picker. DB UNIQUE constraint is a safety net.
2. **Assignee is disabled**: disabled users keep their `sc_assignees` rows and continue to appear in assignee lists (consistent with how a disabled requester still owns the SC). `disable_user` does NOT clean up `sc_assignees`.
3. **Assignee deleted from users table**: FK constraint prevents deletion while rows exist in `sc_assignees`. Admin must remove the assignee from all SCs first. This is expected — deletion is a destructive operation; disabling the user (edge case 2) is the normal flow.
4. **Transfer SC**: assignees stay unchanged. The new requester inherits the same assignee list.
5. **Draft SC visibility**: assignees can see draft SCs (same as the requester). Non-assignee non-admin users cannot see drafts.
