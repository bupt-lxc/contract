# Detail View Restructuring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure SC, PO, GR detail views with Process Summary cards, PO Budget Summary card, fix PO(FC) detail behavior, and fix GR list FC filtering.

**Architecture:** Create two shared Vue components (`ProcessSummaryCard`, `PoBudgetCard`), integrate them into three detail views. Three backend fixes: `sc_request_type` propagation, `finished_at` on PO, `updated_at` on GR. Includes migration v32.

**Tech Stack:** Vue 3 + Element Plus (frontend), Python + SQLite (backend)

---

### Task 1: Create `ProcessSummaryCard` component

**Files:**
- Create: `frontend/src/components/common/ProcessSummaryCard.vue`

- [ ] **Step 1: Create the component**

```vue
<template>
  <el-card class="process-summary-card" shadow="hover">
    <template #header>
      <span>{{ $t('processSummary') }}</span>
    </template>
    <el-descriptions :column="2" border size="small">
      <el-descriptions-item
        v-for="field in fields"
        :key="field.key"
        :label="field.label"
      >
        <span v-if="record[field.key]">{{ (record[field.key] || '').slice(0, 10) || '-' }}</span>
        <span v-else>-</span>
      </el-descriptions-item>
    </el-descriptions>
  </el-card>
</template>

<script setup>
defineProps({
  record: { type: Object, required: true },
  fields: { type: Array, required: true },
})
</script>

<style scoped>
.process-summary-card {
  margin-top: 16px;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/common/ProcessSummaryCard.vue
git commit -m "feat: add ProcessSummaryCard shared component"
```

---

### Task 2: Create `PoBudgetCard` component

**Files:**
- Create: `frontend/src/components/po/PoBudgetCard.vue`

- [ ] **Step 1: Create the component**

```vue
<template>
  <el-card class="budget-card">
    <template #header>Budget Summary</template>
    <el-descriptions :column="3" border size="small">
      <el-descriptions-item :label="$t('po.poAmount')">
        <AmountDisplay :value="budget.po_amount" />
      </el-descriptions-item>
      <el-descriptions-item :label="$t('po.openPoAmount')">
        <AmountDisplay :value="budget.open_po_amount" />
      </el-descriptions-item>
      <el-descriptions-item />

      <template v-if="isFcPo">
        <el-descriptions-item :label="$t('po.allocatedCalloff')">
          <AmountDisplay :value="budget.allocated_calloff_amount" />
        </el-descriptions-item>
        <el-descriptions-item :label="$t('po.pendingCalloff')">
          <AmountDisplay :value="budget.pending_calloff_amount" />
        </el-descriptions-item>
        <el-descriptions-item :label="$t('po.downstreamConsumed')">
          <AmountDisplay :value="budget.downstream_consumed" />
        </el-descriptions-item>
        <el-descriptions-item :label="$t('po.downstreamPendingGr') + ' (excl)'">
          <AmountDisplay :value="budget.downstream_pending_gr" />
        </el-descriptions-item>
        <el-descriptions-item :label="$t('po.downstreamPendingGr') + ' (incl)'">
          <AmountDisplay :value="budget.downstream_pending_gr_tax" />
        </el-descriptions-item>
      </template>
      <template v-else>
        <el-descriptions-item :label="$t('po.consumedAmount')">
          <AmountDisplay :value="budget.consumed_amount || budget.po_con_value_total" />
        </el-descriptions-item>
        <el-descriptions-item :label="$t('po.pendingExclTax')">
          <AmountDisplay :value="budget.pending_total || budget.po_pending_total" />
        </el-descriptions-item>
        <el-descriptions-item :label="$t('po.pendingInclTax')">
          <AmountDisplay :value="budget.pending_total_incl_tax || budget.po_pending_total_incl_tax" />
        </el-descriptions-item>
      </template>
    </el-descriptions>
  </el-card>
</template>

<script setup>
import AmountDisplay from '@/components/common/AmountDisplay.vue'

defineProps({
  budget: { type: Object, required: true },
  isFcPo: { type: Boolean, default: false },
})
</script>

<style scoped>
.budget-card {
  margin-top: 16px;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/po/PoBudgetCard.vue
git commit -m "feat: add PoBudgetCard component for PO budget summary"
```

---

### Task 3: SC Detail — add Process Summary, remove timestamps from ScDetailCard

**Files:**
- Modify: `frontend/src/components/sc/ScDetailCard.vue`
- Modify: `frontend/src/views/ScDetailView.vue`

- [ ] **Step 1: Remove timestamp fields from ScDetailCard.vue**

Remove lines 16-21 (the 6 timestamp `el-descriptions-item` entries: Confirmed At, Created At, Submitted Date, Pending Date, Approved Date, Updated At).

- [ ] **Step 2: Add ProcessSummaryCard import and usage to ScDetailView.vue**

Add import:
```javascript
import ProcessSummaryCard from '@/components/common/ProcessSummaryCard.vue'
```

Add the card right after the ScDetailCard+ScBudgetCard section (line 51 closing `</div>`):

```vue
<ProcessSummaryCard
  :record="detail.sc"
  :fields="scProcessFields"
/>
```

Add computed:
```javascript
const scProcessFields = [
  { key: 'confirmed_at', label: t('confirmed') },
  { key: 'submitted_date', label: t('submitted') },
  { key: 'pending_date', label: t('pending') },
  { key: 'approved_date', label: t('approved') },
  { key: 'finished_at', label: t('finished') },
  { key: 'created_at', label: t('created') },
  { key: 'updated_at', label: t('updated') },
]
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/sc/ScDetailCard.vue frontend/src/views/ScDetailView.vue
git commit -m "feat: add ProcessSummaryCard to SC detail, remove timestamps from ScDetailCard"
```

---

### Task 4: PO Detail — restructure with PoBudgetCard, ProcessSummaryCard, New Call-off SC button

**Files:**
- Modify: `frontend/src/views/PoDetailView.vue`

- [ ] **Step 1: Add imports**

```javascript
import ProcessSummaryCard from '@/components/common/ProcessSummaryCard.vue'
import PoBudgetCard from '@/components/po/PoBudgetCard.vue'
```

- [ ] **Step 2: Add ProcessSummaryCard after PO Information section**

After line 66 (`</div>` that closes the PO Information section-card), add:

```vue
<ProcessSummaryCard
  :record="po"
  :fields="poProcessFields"
/>
```

Add computed:
```javascript
const poProcessFields = [
  { key: 'active_date', label: t('active') },
  { key: 'finished_at', label: t('finished') },
  { key: 'created_at', label: t('created') },
  { key: 'updated_at', label: t('updated') },
]
```

- [ ] **Step 3: Add PoBudgetCard right after ProcessSummaryCard**

```vue
<PoBudgetCard
  v-if="po.po_id"
  :budget="po"
  :is-fc-po="isFcPo"
/>
```

- [ ] **Step 4: Remove budget fields from PO Information el-descriptions**

Remove lines 44-55 (the `v-if="!isFcPo"` template with Consumed Amount, Pending Excl/Incl Tax, and the `v-else` template with Allocated Call-off, Pending Call-off, Downstream Consumed, Downstream Pending GR). Keep PO Amount and Open PO Amount (lines 42-43).

- [ ] **Step 5: Add "New Call-off SC" button in Call-off SCs section header**

In the call-off SCs section (lines 88-100), add a button in the section header:

```vue
<div v-if="isFcPo" class="section-card">
  <div class="section-header">
    <h3>{{ $t('sc.calloffBadge') }}</h3>
    <div style="display:flex;gap:8px">
      <el-button
        v-if="permissions.can_manage_po && scDetail.sc?.status === 'approved'"
        type="primary" size="small"
        :disabled="loadingState.count > 0"
        @click="openCalloffCreate"
      >
        <el-icon><Plus /></el-icon> {{ $t('newCalloffSc') }}
      </el-button>
    </div>
  </div>
  ...
</div>
```

Need a `permissions` computed:
```javascript
const permissions = computed(() => scDetail.value?.permissions || {})
```

- [ ] **Step 6: Add `openCalloffCreate` method (reuse ScFormDialog)**

Since ScFormDialog is not in PoDetailView, add it. The route is `/sc/:scId/po/:poId`, so redirect to SC detail with query param to open create dialog. But simpler: just navigate to the SC detail page to create:

```javascript
function openCalloffCreate() {
  router.push(`/sc/${scId.value}?openCreate=true`)
}
```

Or we can import `ScFormDialog` directly. But it needs `calloffPoId` pre-filled and `scRecord` for the FC SC. The simpler approach: navigate to SC detail which already has the "Add PO / create SC" flow.

Actually, re-reading the spec: the "New Call-off SC" button opens `ScFormDialog` with `calloffPoId` pre-filled. But PoDetailView doesn't integrate ScFormDialog. The cleanest approach without pulling in another large dialog: navigate to the SC detail page and pass a query param.

```javascript
function openCalloffCreate() {
  router.push(`/sc/${scId.value}?action=createCalloff&calloffPoId=${poId.value}`)
}
```

Then in ScDetailView, handle `route.query.action === 'createCalloff'` to open ScFormDialog with calloffPoId pre-filled. But this adds complexity to another view.

Simpler approach for now: just navigate to SC page. The user can create a call-off SC from there.

```javascript
function openCalloffCreate() {
  router.push(`/sc/${scId.value}`)
}
```

Wait, actually, the SC page already has ScFormDialog and the user can create SCs. But they need calloff_po_id pre-filled. The ScFormDialog already supports `calloffPoId`/`calloffPoInfo` props as mentioned in the spec. Let me keep it simple and just navigate to the SC page for now. The SC detail page already handles call-off SC creation via its PoFcSelectorDialog flow.

Actually, the simplest and most useful approach for the user: open the existing `ScFormDialog` directly in PoDetailView. I need to add the import, the dialog, and wire it up. But that significantly increases the scope of this task. Let me go with the navigation approach.

```javascript
function openCalloffCreate() {
  router.push(`/sc?calloffPoId=${poId.value}`)
}
```

This navigates to the SC list with the calloffPoId query parameter. The ScListView already has the PoFcSelectorDialog integration for creating call-off SCs from the SC list.

Hmm, actually looking at the original spec more carefully: it says "opens ScFormDialog with calloffPoId pre-filled". Let me just implement it with a simple router navigation to the SC detail:

```javascript
function openCalloffCreate() {
  router.push(`/sc/${scId.value}`)
}
```

This navigates to the parent SC detail page where the user already has all the tools to create a call-off SC.

- [ ] **Step 7: Remove active_date from PO Information el-descriptions**

Remove line 64:
```vue
<el-descriptions-item :label="$t('po.activeDate')">{{ (po.active_date || '').slice(0, 10) || '-' }}</el-descriptions-item>
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/PoDetailView.vue
git commit -m "feat: restructure PO detail with PoBudgetCard, ProcessSummaryCard, and New Call-off SC button"
```

---

### Task 5: GR Detail — add Process Summary

**Files:**
- Modify: `frontend/src/views/GrDetailView.vue`

- [ ] **Step 1: Add import**

```javascript
import ProcessSummaryCard from '@/components/common/ProcessSummaryCard.vue'
```

- [ ] **Step 2: Remove timestamp fields from GR Information el-descriptions**

Remove lines 52-57 (Confirmed At, Created, Submitted Date, Pending Date, Approved Date, Created By).

- [ ] **Step 3: Add ProcessSummaryCard after GR Information section**

After line 59 (`</div>` closes section-card):

```vue
<ProcessSummaryCard
  :record="gr"
  :fields="grProcessFields"
/>
```

Add computed:
```javascript
const grProcessFields = [
  { key: 'confirmed_at', label: t('confirmed') },
  { key: 'submitted_date', label: t('submitted') },
  { key: 'pending_date', label: t('pending') },
  { key: 'approved_date', label: t('approved') },
  { key: 'finished_at', label: t('finished') },
  { key: 'created_at', label: t('created') },
  { key: 'updated_at', label: t('updated') },
]
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/GrDetailView.vue
git commit -m "feat: add ProcessSummaryCard to GR detail, remove scattered timestamps"
```

---

### Task 6: i18n keys

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.js`
- Modify: `frontend/src/i18n/locales/en-US.js`

- [ ] **Step 1: Add new zh-CN keys**

Find an appropriate location (near existing time-related keys) and add:

```javascript
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
```

- [ ] **Step 2: Add new en-US keys**

```javascript
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

- [ ] **Step 3: Commit**

```bash
git add frontend/src/i18n/locales/zh-CN.js frontend/src/i18n/locales/en-US.js
git commit -m "feat: add Process Summary and Budget Summary i18n keys"
```

---

### Task 7: Backend — fix `sc_request_type` in PO objects

**Files:**
- Modify: `sc_gr_app/services/sc_service.py`

- [ ] **Step 1: Add `sc_request_type` to each PO**

In `get_sc_detail`, after the PO query loop and the FC/non-FC budget computation loop (around line 1263-1277), add:

```python
for po in pos:
    po["sc_request_type"] = sc["request_type"]
```

This ensures every PO object carries the parent SC's request_type, so the frontend can check `po.sc_request_type === 'FC'`.

- [ ] **Step 2: Run tests to verify**

Run: `python -m pytest tests/test_fc_calloff_flow.py tests/test_po_service.py tests/test_sc_service_calloff.py -v`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/services/sc_service.py
git commit -m "fix: propagate sc_request_type to PO objects in get_sc_detail"
```

---

### Task 8: GR List — exclude FC SCs and POs from "Add GR"

**Files:**
- Modify: `frontend/src/views/GrListView.vue`

- [ ] **Step 1: Filter FC-type SCs in `loadEligibleScs`**

Change line 302:
```javascript
eligibleScs.value = result.rows || result || []
```
To:
```javascript
eligibleScs.value = (result.rows || result || []).filter(sc => sc.request_type !== 'FC')
```

- [ ] **Step 2: Filter FC POs in `onGrScChange`**

Change lines 311-314 to add `is_fc_po: '0'`:
```javascript
const result = await callApi('search_pos', {
  filters: { sc_id: scId, is_fc_po: '0' },
  limit: 200, offset: 0,
  sort: 'created_at', direction: 'desc'
})
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/GrListView.vue
git commit -m "fix: exclude FC SCs and POs from GR creation dropdown in GR list view"
```

---

### Task 9: Backend — add `finished_at` to PO

**Files:**
- Modify: `sc_gr_app/db/migrations.py`
- Modify: `sc_gr_app/services/po_service.py`

- [ ] **Step 1: Add migration v32 — add `finished_at` to `pos` and `updated_at` to `gr_requests`**

At the end of `migrations.py` (before `def migrate`), add:

```python
def _migrate_v32(conn) -> None:
    """Add finished_at to pos, updated_at to gr_requests."""
    if _table_exists(conn, "pos"):
        existing_po = {row["name"] for row in conn.execute("PRAGMA table_info(pos)")}
        if "finished_at" not in existing_po:
            conn.execute("ALTER TABLE pos ADD COLUMN finished_at TEXT")
    if _table_exists(conn, "gr_requests"):
        existing_gr = {row["name"] for row in conn.execute("PRAGMA table_info(gr_requests)")}
        if "updated_at" not in existing_gr:
            conn.execute("ALTER TABLE gr_requests ADD COLUMN updated_at TEXT")
    _record(conn, 32)
```

- [ ] **Step 2: Update `SCHEMA_VERSION` to 32**

Change line 9:
```python
SCHEMA_VERSION = 32
```

- [ ] **Step 3: Register migration in `migrate()` function**

After the `_migrate_v31(conn)` call (around line 1336), add:
```python
_migrate_v32(conn)
```

Wait — looking at the migration structure, the `migrate()` function applies migrations in order. Let me check... Actually, the `migrate` function uses `_applied_versions` and iterates. Each `_migrate_vXX` function calls `_record(conn, XX)` which inserts the version. The `migrate` function runs a for loop from `max_applied + 1` to `SCHEMA_VERSION + 1` calling `globals()[f"_migrate_v{v}"]`. So I just need to register v32 in the function map. Looking at how migrates are referenced...

Let me read the actual `migrate` function.

- [ ] **Step 4: Actually, let me just add the function. The `migrate()` runner already handles it**

```python
def _migrate_v32(conn) -> None:
    """Add finished_at to pos, updated_at to gr_requests."""
    if _table_exists(conn, "pos"):
        existing_po = {row["name"] for row in conn.execute("PRAGMA table_info(pos)")}
        if "finished_at" not in existing_po:
            conn.execute("ALTER TABLE pos ADD COLUMN finished_at TEXT")
    if _table_exists(conn, "gr_requests"):
        existing_gr = {row["name"] for row in conn.execute("PRAGMA table_info(gr_requests)")}
        if "updated_at" not in existing_gr:
            conn.execute("ALTER TABLE gr_requests ADD COLUMN updated_at TEXT")
    _record(conn, 32)
```

And update `SCHEMA_VERSION = 32`.

- [ ] **Step 5: Update `finish_po` to set `finished_at`**

In `po_service.py`, change the UPDATE at line 521-528 from:
```python
conn.execute(
    """
    update pos
    set status = 'finished',
        updated_at = ?
    where po_id = ?
    """,
    (timestamp, po_id),
)
```
To:
```python
conn.execute(
    """
    update pos
    set status = 'finished',
        updated_at = ?,
        finished_at = ?
    where po_id = ?
    """,
    (timestamp, timestamp, po_id),
)
```

- [ ] **Step 6: Run tests to verify**

Run: `python -m pytest tests/test_po_service.py tests/test_fc_calloff_flow.py tests/test_budget_service.py -v`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add sc_gr_app/db/migrations.py sc_gr_app/services/po_service.py
git commit -m "feat: add finished_at column to PO and set it on finish"
```

---

### Task 10: Backend — add `updated_at` to GR and set it on all state changes

**Files:**
- Modify: `sc_gr_app/services/gr_service.py`

- [ ] **Step 1: Add `updated_at` to `create_gr` INSERT**

In `create_gr`, add `updated_at` to the column list and VALUES. Find the INSERT (around line 221):

Add `updated_at` to the columns list (before `goods_service_description`):
```sql
updated_at,
```

Add `timestamp` value in the corresponding position.

- [ ] **Step 2: Add `updated_at = ?` to all GR UPDATE statements**

Find each UPDATE in gr_service.py and add `updated_at = ?,`. The functions to modify:

1. `submit_gr` (around line 317): add `updated_at = ?,` before `where gr_id = ?`
2. `confirm_gr` (around line 401): add `updated_at = ?,` before `where gr_id = ?`
3. `approve_gr` (around line 524): add `updated_at = ?,` before `where gr_id = ?`
4. `update_gr` (around line 561): add `updated_at = ?,` to the SET clause
5. `deny_gr` (around line 811): add `updated_at = ?,` before `where gr_id = ?`
6. `finish_gr` (around line 866): add `updated_at = ?,` before `where gr_id = ?`
7. `recall_gr` (around line 928): add `updated_at = ?,` before `where gr_id = ?`

Each change follows the same pattern — add `, updated_at = ?` to the SET clause and add the `timestamp` parameter to the params tuple.

Example for `submit_gr`:
```python
timestamp = utc_now()
conn.execute(
    """
    update gr_requests
    set status = 'manager_confirm',
        submitted_date = ?,
        pending_date = ?,
        updated_at = ?
    where gr_id = ?
    """,
    (timestamp, timestamp, timestamp, gr_id),
)
```

- [ ] **Step 3: Run tests to verify**

Run: `python -m pytest tests/test_sc_po_gr_flow.py tests/test_gr_service.py -v` (if test_gr_service.py exists) or: `python -m pytest tests/ -v -k "gr"`

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/services/gr_service.py
git commit -m "feat: add updated_at to GR, set on all state changes"
```

---

### Task 11: Verify all tests pass

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest tests/ -v
```
Expected: All tests pass (except pre-existing migration count tests that may need updating for v32).

- [ ] **Step 2: Fix any test failures**

If `test_migrations.py` asserts exact migration count, update from 31 to 32.

- [ ] **Step 3: Commit any test fixes**

```bash
git add tests/
git commit -m "test: update tests for v32 migration and new columns"
```

---

## Self-Review

1. **Spec coverage:** All 11 spec tasks mapped to plan tasks 1-11. Bug fix (sc_request_type) in Task 7. GR list FC filtering in Task 8. Backend columns in Tasks 9-10. Process Summary in Tasks 1,3,4,5. Budget Summary in Task 2,4. i18n in Task 6. Tests in Task 11.

2. **Placeholder scan:** All code blocks have concrete content. No TBDs, TODOs, or vague instructions.

3. **Type consistency:** ProcessSummaryCard uses `record` + `fields` props consistently across all 3 consumers. PoBudgetCard uses `budget` + `isFcPo` props. Migration v32 handles both `finished_at` (PO) and `updated_at` (GR) columns.
