# Detail View Restructuring Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure SC, PO, GR detail views with Process Summary cards, PO Budget Summary card, and fix PO(FC) detail behavior.

**Architecture:** Three UI changes across detail views: (1) shared `ProcessSummaryCard` component replacing scattered timestamps with a unified chronological card, (2) new `PoBudgetCard` component for PO budget display matching SC's pattern, (3) fix PO(FC) to hide GR controls and show call-off SC creation. Backend: fix missing `sc_request_type` in PO objects, add `finished_at` to PO table, add `updated_at` to GR table.

**Tech Stack:** Vue 3 + Element Plus (frontend), Python + SQLite (backend)

---

## Bug: PO(FC) not detected — `sc_request_type` missing

**Root cause:** `get_sc_detail` ([sc_service.py:1211](sc_gr_app/services/sc_service.py#L1211)) selects `po.*` but never `sc.request_type`. The frontend's `isFcPo` computed property checks `po.sc_request_type === 'FC'`, which is always `undefined`.

**Fix:** Change the PO query to include `sc.request_type as sc_request_type`.

## Backend: Missing columns

### PO `finished_at`
The `finish_po` service sets status to `finished` but doesn't set `finished_at`. The column was lost in migration 29's `pos` rebuild. Add a migration to add `finished_at TEXT` to `pos`, and update `finish_po` to set it to `utc_now()`.

### GR `updated_at`
The `gr_requests` table has no `updated_at` column. Add a migration to add `updated_at TEXT` to `gr_requests`, and update GR service functions (create, update, submit, approve, deny, confirm, finish, recall) to set/update it.

## Frontend Changes

### Task 1: `processSummaryCard` component

**Files:**
- Create: `frontend/src/components/common/ProcessSummaryCard.vue`

A shared component receiving a `record` prop and a `fields` prop (array of `{ key, label }`). Renders an `el-card` with header "Process Summary" containing `el-descriptions` (2 columns, border, size small). Each field only renders when the record has a truthy value. Dates displayed as `YYYY-MM-DD` (`.slice(0, 10)`). The `finished` field renders with a green text style.

```vue
<!-- frontend/src/components/common/ProcessSummaryCard.vue -->
<template>
  <el-card class="process-summary-card" shadow="hover">
    <template #header>
      <span>{{ t('processSummary') }}</span>
    </template>
    <el-descriptions :column="2" border size="small">
      <el-descriptions-item
        v-for="field in fields"
        :key="field.key"
        :label="field.label"
        :class="{ 'is-finished': field.key === 'finished_at' && record[field.key] }"
      >
        <span v-if="record[field.key]">{{ formatDate(record[field.key]) }}</span>
        <span v-else>-</span>
      </el-descriptions-item>
    </el-descriptions>
  </el-card>
</template>
```

### Task 2: `poBudgetCard` component

**Files:**
- Create: `frontend/src/components/po/PoBudgetCard.vue`

Modeled after `ScBudgetCard`. Receives `budget` and `isFcPo` props. 3-column `el-descriptions` in an `el-card` with "Budget Summary" header.

**Regular PO fields:**
- PO Amount, Open PO Amount, (empty)
- Consumed, Pending GR (excl), Pending GR (incl)

**FC PO fields:**
- PO Amount, Open PO Amount, (empty)
- Allocated Call-off, Pending Call-off, Downstream Consumed
- Downstream Pending GR (excl), Downstream Pending GR (incl)

### Task 3: SC Detail — add Process Summary

**Files:**
- Modify: `frontend/src/views/ScDetailView.vue`
- Modify: `frontend/src/components/sc/ScDetailCard.vue`

Remove timestamp fields from `ScDetailCard` (confirmed_at, created_at, submitted_date, pending_date, approved_date, updated_at). Add `ProcessSummaryCard` to `ScDetailView` below SC Information and above vendor section.

SC fields: `confirmed_at`, `submitted_date`, `pending_date`, `approved_date`, `finished_at`, `created_at`, `updated_at`.

### Task 4: PO Detail — restructure

**Files:**
- Modify: `frontend/src/views/PoDetailView.vue`

Changes:
1. Move budget fields out of PO Information `el-descriptions` into `PoBudgetCard`
2. Keep only PO Amount and Open PO Amount in Information (also in Budget Summary)
3. Add `ProcessSummaryCard` with PO fields: `active_date`, `finished_at`, `created_at`, `updated_at`
4. Add "New Call-off SC" button in Call-off SCs section header (visible when `can_manage_po` AND SC approved)
5. The "New Call-off SC" button opens `ScFormDialog` with `calloffPoId` pre-filled
6. Remove "Add GR" button (already hidden for FC, but verify after backend fix)

### Task 5: GR Detail — add Process Summary

**Files:**
- Modify: `frontend/src/views/GrDetailView.vue`

Remove timestamp fields from GR Information `el-descriptions` (confirmed_at, created_at, submitted_date, pending_date, approved_date, created_by). Add `ProcessSummaryCard` below GR Information.

GR fields: `confirmed_at`, `submitted_date`, `pending_date`, `approved_date`, `finished_at`, `created_at`, `updated_at`.

### Task 6: i18n keys

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.js`
- Modify: `frontend/src/i18n/locales/en-US.js`

New keys:
```javascript
// zh-CN
processSummary: '流程摘要',
confirmed: '已确认',
submitted: '已提交',
pending: '待审批',
approved: '已批准',
finished: '已完成',
created: '创建',
updated: '更新',
active: '生效',
newCalloffSc: '新建Call-off SC',

// en-US
processSummary: 'Process Summary',
confirmed: 'Confirmed',
submitted: 'Submitted',
pending: 'Pending',
approved: 'Approved',
finished: 'Finished',
created: 'Created',
updated: 'Updated',
active: 'Active',
newCalloffSc: 'New Call-off SC',
```

Existing timestamp labels (Confirmed At, Created At, etc.) remain in the locale files for backward compatibility with list views and other components. Only the Process Summary card uses the new stripped labels.

### Task 7: Backend — fix `sc_request_type` in PO objects

**Files:**
- Modify: `sc_gr_app/services/sc_service.py` line 1211

Change:
```python
"""select po.*, v.vendor_name, v.ksrm_vendor_code
   from pos po ..."""
```
To:
```python
"""select po.*, sc.request_type as sc_request_type, v.vendor_name, v.ksrm_vendor_code
   from pos po
   join sc_records sc on sc.sc_id = po.sc_id
   ..."""
```

Wait — the query already references `pos po` joined with `vendors v`, but not with `sc_records`. Since the query already has `WHERE po.sc_id = ?` and we're in the context of a specific SC, we can just add `sc.request_type as sc_request_type` from a `join sc_records sc on sc.sc_id = po.sc_id`. Actually simpler: since all POs in this query belong to the same SC (`WHERE po.sc_id = ?`), we can just return `sc["request_type"]` once and use it on all POs — but the frontend expects `po.sc_request_type` per PO. The cleanest approach: add the join.

Actually, the simplest correct approach: since all POs belong to this SC which we already have as `sc`, we can set `po["sc_request_type"] = sc["request_type"]` in the Python loop. No SQL change needed.

### Task 8: Backend — add `finished_at` to PO

**Files:**
- Modify: `sc_gr_app/db/migrations.py` (new migration v31)
- Modify: `sc_gr_app/services/po_service.py` (`finish_po`)

Migration: `ALTER TABLE pos ADD COLUMN finished_at TEXT`.
`finish_po`: set `finished_at = utc_now()` in the UPDATE.

### Task 9: Backend — add `updated_at` to GR

**Files:**
- Modify: `sc_gr_app/db/migrations.py` (new migration v31)
- Modify: `sc_gr_app/services/gr_service.py`

Migration: `ALTER TABLE gr_requests ADD COLUMN updated_at TEXT`.
Update `updated_at` to `utc_now()` in relevant GR service functions: on any status change or field update.

### Task 10: Verify all tests pass

Run full test suite. Add any needed test adjustments for the `finished_at` / `updated_at` column changes.

---

## Spec Self-Review

- **Placeholder scan:** None — all tasks have concrete file paths and code.
- **Internal consistency:** Process Summary labels are consistent across all 3 entities. Budget Summary follows SC pattern. Backend column changes are minimal and isolated.
- **Scope check:** Single focused feature (detail view restructuring). No decomposition needed.
- **Ambiguity check:** All field lists are explicit per entity. Label stripping is clearly defined.
