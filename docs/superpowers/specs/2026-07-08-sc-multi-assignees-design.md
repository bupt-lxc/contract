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
| `_sc_permissions` | Assignees get `can_view = true`; all operational permissions (`can_edit_sc`, `can_submit_sc`, etc.) remain `false` |
| `create_sc_draft` | Accept `assignee_ids` in data, call `_sync_sc_assignees` after insert |
| `update_sc` | Accept `assignee_ids` in data, call `_sync_sc_assignees` |
| `submit_sc` | Accept `assignee_ids` in merged data, call `_sync_sc_assignees` |
| `_sync_sc_assignees(conn, sc_id, assignee_ids)` | New helper — DELETE all existing, INSERT new list (same pattern as `_sync_sc_vendors`) |
| `get_sc_detail` | Return `assignees` list (user_id, user_name from users table) |
| `transfer_sc` | No change — only primary requester is transferred |

### query_service.py

Non-admin workbench and search WHERE clauses change from:

```
sc.requester_id = ?
```

to:

```
(sc.requester_id = ? OR sc.sc_id IN (SELECT sc_id FROM sc_assignees WHERE user_id = ?))
```

### notification_service.py

Status-change notifications include assignees as additional recipients (CC, not To — the primary requester remains the To recipient).

### API bridge (bridge.py)

- `create_sc_draft`, `update_sc`, `submit_sc`: extract `assignee_ids` from payload data
- `get_sc_detail`: return assignees in response
- New endpoint: none needed (assignees are managed through existing create/update/submit endpoints)

### schemas.py (OPTIONAL_UPDATE_FIELDS)

Add `"assignee_ids"` to the list of optional update fields.

## Frontend Changes

### ScFormDialog.vue

- Add `<el-select multiple>` for assignee selection below the requester dropdown
- Label: "协作者" / "Assignees"
- Data binding: `form.assignee_ids`

### ScDetailCard.vue

- Show assignee list below requester field
- Format: comma-separated user names

### ScTable.vue

- No required change (requester_name column stays as the primary owner)
- Optional: could show an indicator if assignees exist

## What Does NOT Change

- `create_sc` (direct submit flow)
- `approve_sc`, `deny_sc`, `finish_sc`, `confirm_sc`, `recall_sc`, `delete_sc`
- Import/export templates and logic
- The `transfer_sc` function
- All existing `requester_id`-based permission checks for write operations

## Edge Cases

1. **Primary requester also listed as assignee**: harmless no-op — the requester already has full access; UI should prevent selection of the requester in the assignee picker.
2. **Assignee is disabled**: still shows in the list; view permissions still granted (consistent with how disabled requester works).
3. **Assignee deleted from users table**: FK constraint prevents deletion while rows exist in `sc_assignees`. Admin must remove the assignee from SCs first, or we cascade on user disable.
4. **Transfer SC**: assignees stay unchanged after transfer. The new requester inherits the same assignee list.
