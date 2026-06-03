# Batch Operations — Design Spec

## Overview

Add checkbox-based row selection and batch actions (submit, confirm, approve) to the SC and GR list views. No backend changes — frontend loops over existing single-item APIs with best-effort error handling and a result summary.

## Scope

- **SC list view**: batch submit (draft → manager_confirm), batch confirm (manager_confirm → pending), batch approve (pending → approved)
- **GR list view**: batch submit (draft → manager_confirm), batch confirm (manager_confirm → pending)
- **GR batch approve excluded**: `approve_gr` requires a per-row `con_value` input; keep single-item for now
- **PO list view excluded**: PO has a different workflow (draft → activing → finished) and is out of scope

## Approach

Frontend-only: iterate selected rows, call existing single-item bridge methods serially, collect per-row results, display a summary. No new backend endpoints.

Rationale: existing per-item APIs already handle locking, validation, audit logging, and notification correctly. For typical batch sizes (5–20 items), N API calls add negligible overhead.

## UI Design

### Batch Action Bar

Appears between the filter bar and the table whenever one or more rows are checked:

```
已选择 5 项  |  [批量提交] [批量确认] [批量审批]
```

- Shows count of selected rows
- Each button is visible only when at least one selected row qualifies for that action
- Buttons call `runBatch()` with the filtered subset of rows

### Flow

1. User checks rows via checkbox column
2. Clicks a batch action button
3. Confirmation dialog: "批量提交选中的 N 项?" (or confirm/approve)
4. Processes serially in the background (no progress bar needed for < 20 items)
5. Result summary dialog via `ElMessageBox.alert`

### Result Summary

```
批量提交完成

✓ 成功: 7 项
✗ 失败: 3 项

失败详情:
  SC-2026001-001: SC must be draft to submit
  SC-2026001-005: SC No is required
  SC-2026001-008: Permission denied
```

## Component Changes

### New: `frontend/src/composables/useBatchAction.js`

```javascript
export function useBatchAction() {
  async function runBatch(rows, actionName, actionFn) {
    // 1. Confirm with user
    // 2. Process serially, catch per-row errors
    // 3. Return { total, succeeded, failed: [{id, reason}] }
  }
  return { runBatch }
}
```

- `rows`: array of selected row objects
- `actionName`: display name for the confirm dialog ("提交" / "确认" / "审批")
- `actionFn`: async `(row) => result` — calls the appropriate bridge method
- Returns structured result for the view to format and display

### Modified: `frontend/src/components/sc/ScTable.vue`

Add `selectable` prop (Boolean, default false). When true, render an `<el-table-column type="selection" width="50" />` as the first column.

### Modified: `frontend/src/views/ScListView.vue`

- Add `selectedRows` ref, `@selection-change` handler on `<ScTable>`
- Add batch action bar markup (visible when `selectedRows.length > 0`)
- Import `useBatchAction`, wire up three batch buttons calling `submit_sc` / `confirm_sc` / `approve_sc`
- After batch completes, refresh the list

### Modified: `frontend/src/views/GrListView.vue`

- Add `type="selection"` column to the inline `<el-table>`
- Same batch action bar and wiring as ScListView, but only submit and confirm actions
- API calls: `submit_gr` / `confirm_gr`

## Permissions

No new permission checks. Each single-item API already validates:
- `submit_sc`/`submit_gr`: requester or admin, must be draft
- `confirm_sc`/`confirm_gr`: admin only, must be manager_confirm
- `approve_sc`: admin only, must be pending, sc_no required

Rows that fail the API's own permission/business-rule checks are caught and reported in the summary.

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/composables/useBatchAction.js` | New composable |
| `frontend/src/components/sc/ScTable.vue` | Add `selectable` prop, checkbox column |
| `frontend/src/views/ScListView.vue` | Selection state, batch bar, wiring |
| `frontend/src/views/GrListView.vue` | Selection state, batch bar, wiring |
| `frontend/src/i18n/locales/zh-CN.js` | Batch-related i18n keys |
| `frontend/src/i18n/locales/en-US.js` | Batch-related i18n keys |

## i18n Keys

| Key | zh-CN | en-US |
|-----|-------|-------|
| `batch.selected` | 已选择 {count} 项 | {count} selected |
| `batch.submit` | 批量提交 | Batch Submit |
| `batch.confirm` | 批量确认 | Batch Confirm |
| `batch.approve` | 批量审批 | Batch Approve |
| `batch.submitConfirm` | 确认批量提交选中的 {count} 项? | Submit {count} selected items? |
| `batch.confirmConfirm` | 确认批量确认选中的 {count} 项? | Confirm {count} selected items? |
| `batch.approveConfirm` | 确认批量审批选中的 {count} 项? | Approve {count} selected items? |
| `batch.result` | 批量{action}完成 | Batch {action} complete |
| `batch.success` | 成功: {count} 项 | Success: {count} |
| `batch.failed` | 失败: {count} 项 | Failed: {count} |
| `batch.failDetail` | 失败详情 | Failure Details |

## Backward Compatibility

- All existing behavior unchanged when no rows are selected
- ScTable `selectable` defaults to false — other consumers unaffected
- PO list view unchanged

## Verification

- Manual testing: select SCs in different statuses, verify only qualified rows are processed
- Manual testing: select GRs, verify submit + confirm work and approve is absent
- Edge case: select 0 rows → batch bar hidden
- Edge case: select rows but none qualify for chosen action → all skipped, reported
- Edge case: network error during processing → caught per-row, reported
- Existing tests continue to pass (no backend changes)
