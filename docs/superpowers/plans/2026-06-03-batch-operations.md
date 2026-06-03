# Batch Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add checkbox-based row selection and batch submit/confirm/approve actions to SC and GR list views, with a blocking progress modal and abort support.

**Architecture:** Frontend-only — loops over existing single-item bridge APIs serially. New `useBatchAction` composable manages all batch state and logic. New `BatchProgressModal` component renders the blocking progress dialog. Both ScListView and GrListView wire up the composable + modal, sharing no duplicated logic.

**Tech Stack:** Vue 3 + Element Plus + vue-i18n

---

## File Structure

| File | Responsibility |
|------|---------------|
| `frontend/src/composables/useBatchAction.js` | Reactive batch state, serial processing loop, abort control, result formatting |
| `frontend/src/components/common/BatchProgressModal.vue` | Reusable blocking progress dialog (el-dialog), binds to composable state |
| `frontend/src/components/sc/ScTable.vue` | Add `selectable` prop for checkbox column |
| `frontend/src/views/ScListView.vue` | Selection state, batch bar UI, wire submit/confirm/approve |
| `frontend/src/views/GrListView.vue` | Selection state, batch bar UI, wire submit/confirm only |
| `frontend/src/i18n/locales/zh-CN.js` | Batch i18n keys (Chinese) |
| `frontend/src/i18n/locales/en-US.js` | Batch i18n keys (English) |

---

### Task 1: Add i18n keys

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.js`
- Modify: `frontend/src/i18n/locales/en-US.js`

- [ ] **Step 1: Add batch keys to zh-CN.js**

Add a `batch` section after the `attachment` block (before the closing `};` of the default export):

```javascript
batch: {
    selected: '已选择 {count} 项',
    submit: '批量提交',
    confirm: '批量确认',
    approve: '批量审批',
    submitConfirm: '确认批量提交选中的 {count} 项？',
    confirmConfirm: '确认批量确认选中的 {count} 项？',
    approveConfirm: '确认批量审批选中的 {count} 项？',
    result: '批量{action}完成',
    success: '成功: {count} 项',
    failed: '失败: {count} 项',
    failDetail: '失败详情',
    processing: '正在处理 {current}/{total}',
    completed: '已完成: {count}',
    skipped: '已跳过: {count}',
    abort: '终止操作',
    aborted: '用户终止',
    noQualifying: '所选项目中没有符合批量{action}条件的记录',
    titleSubmit: '批量提交',
    titleConfirm: '批量确认',
    titleApprove: '批量审批'
},
```

- [ ] **Step 2: Add batch keys to en-US.js**

Add a `batch` section after the `attachment` block:

```javascript
batch: {
    selected: '{count} selected',
    submit: 'Batch Submit',
    confirm: 'Batch Confirm',
    approve: 'Batch Approve',
    submitConfirm: 'Submit {count} selected items?',
    confirmConfirm: 'Confirm {count} selected items?',
    approveConfirm: 'Approve {count} selected items?',
    result: 'Batch {action} Complete',
    success: 'Success: {count}',
    failed: 'Failed: {count}',
    failDetail: 'Failure Details',
    processing: 'Processing {current}/{total}',
    completed: 'Completed: {count}',
    skipped: 'Skipped: {count}',
    abort: 'Abort',
    aborted: 'Aborted by user',
    noQualifying: 'No selected items qualify for batch {action}',
    titleSubmit: 'Batch Submit',
    titleConfirm: 'Batch Confirm',
    titleApprove: 'Batch Approve'
},
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/i18n/locales/zh-CN.js frontend/src/i18n/locales/en-US.js
git commit -m "feat: add batch operations i18n keys for zh-CN and en-US"
```

---

### Task 2: Create useBatchAction composable

**Files:**
- Create: `frontend/src/composables/useBatchAction.js`

- [ ] **Step 1: Write the composable**

```javascript
import { reactive, ref } from 'vue'
import { ElMessageBox } from 'element-plus'

export function useBatchAction() {
  const state = reactive({
    active: false,
    total: 0,
    current: 0,
    currentId: '',
    succeeded: 0,
    failed: 0,
    skipped: 0,
    failedItems: [],
    aborted: false
  })

  const abortController = ref(null)

  function getEntityId(row) {
    return row.sc_id || row.gr_id || row.po_id || ''
  }

  function qualifyRows(rows, action) {
    const qualifiers = {
      submit: r => r.status === 'draft',
      confirm: r => r.status === 'manager_confirm',
      approve: r => r.status === 'pending'
    }
    const fn = qualifiers[action]
    return fn ? rows.filter(fn) : []
  }

  async function runBatch(rows, actionName, actionFn, t) {
    const qualifying = qualifyRows(rows, actionName)
    if (!qualifying.length) {
      await ElMessageBox.alert(
        t('batch.noQualifying', { action: t(`batch.${actionName}`) }),
        t('common.confirm')
      )
      return null
    }

    const confirmMessages = {
      submit: 'batch.submitConfirm',
      confirm: 'batch.confirmConfirm',
      approve: 'batch.approveConfirm'
    }
    try {
      await ElMessageBox.confirm(
        t(confirmMessages[actionName], { count: qualifying.length }),
        t('common.confirm'),
        { type: 'warning' }
      )
    } catch {
      return null // user cancelled
    }

    // Reset state
    state.active = true
    state.total = qualifying.length
    state.current = 0
    state.currentId = ''
    state.succeeded = 0
    state.failed = 0
    state.skipped = 0
    state.failedItems = []
    state.aborted = false
    abortController.value = new AbortController()
    const signal = abortController.value.signal

    for (let i = 0; i < qualifying.length; i++) {
      if (signal.aborted) {
        state.skipped += qualifying.length - i
        state.aborted = true
        break
      }
      const row = qualifying[i]
      state.current = i + 1
      state.currentId = getEntityId(row)
      try {
        await actionFn(row)
        state.succeeded++
      } catch (e) {
        state.failed++
        state.failedItems.push({
          id: getEntityId(row),
          reason: e.message || String(e)
        })
      }
    }

    state.active = false
    abortController.value = null

    return {
      total: state.total,
      succeeded: state.succeeded,
      failed: state.failed,
      skipped: state.skipped,
      failedItems: state.failedItems,
      aborted: state.aborted
    }
  }

  function abort() {
    abortController.value?.abort()
  }

  return { state, runBatch, abort }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/composables/useBatchAction.js
git commit -m "feat: add useBatchAction composable for batch processing"
```

---

### Task 3: Create BatchProgressModal component

**Files:**
- Create: `frontend/src/components/common/BatchProgressModal.vue`

- [ ] **Step 1: Write the component**

```vue
<template>
  <el-dialog
    :model-value="visible"
    :title="title"
    width="420px"
    :close-on-click-modal="false"
    :show-close="false"
  >
    <div style="text-align:center;padding:12px 0">
      <p style="margin-bottom:8px;font-size:15px;color:#303133">
        {{ $t('batch.processing', { current: state.current, total: state.total }) }}
      </p>
      <p style="margin-bottom:16px;font-size:13px;color:#909399;font-family:monospace">
        {{ state.currentId }}
      </p>
      <div style="display:flex;justify-content:center;gap:24px;margin-bottom:16px">
        <span style="color:#67c23a;font-size:14px">
          {{ $t('batch.completed', { count: state.succeeded }) }}
        </span>
        <span style="color:#f56c6c;font-size:14px">
          {{ $t('batch.skipped', { count: state.failed + state.skipped }) }}
        </span>
      </div>
      <el-button type="danger" plain @click="$emit('abort')">
        {{ $t('batch.abort') }}
      </el-button>
    </div>
  </el-dialog>
</template>

<script setup>
defineProps({
  visible: { type: Boolean, default: false },
  title: { type: String, default: '' },
  state: { type: Object, required: true }
})

defineEmits(['abort'])
</script>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/common/BatchProgressModal.vue
git commit -m "feat: add BatchProgressModal component for blocking batch progress UI"
```

---

### Task 4: Add selectable prop to ScTable

**Files:**
- Modify: `frontend/src/components/sc/ScTable.vue`

- [ ] **Step 1: Add selectable prop and checkbox column**

In the `<script setup>`, add `selectable` to `defineProps`:

```javascript
const props = defineProps({
  rows: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  emptyText: { type: String, default: 'No SC records match the search and filters.' },
  selectable: { type: Boolean, default: false }
})
```

In the `<template>`, add a checkbox column as the first `<el-table-column>` (before the status column):

```html
<el-table-column v-if="selectable" type="selection" width="50" />
```

Also add `@selection-change` emit forwarding to `<el-table>`:

```html
<el-table
    :data="rows"
    v-loading="loading"
    stripe
    border
    @sort-change="$emit('sort-change', $event)"
    @row-click="$emit('row-click', $event)"
    @selection-change="$emit('selection-change', $event)"
    :row-class-name="rowClass"
    style="cursor:pointer"
  >
```

Add `'selection-change'` to the `defineEmits` array:

```javascript
defineEmits(['sort-change', 'row-click', 'selection-change'])
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/sc/ScTable.vue
git commit -m "feat: add selectable prop and selection-change emit to ScTable"
```

---

### Task 5: Wire batch operations into ScListView

**Files:**
- Modify: `frontend/src/views/ScListView.vue`

- [ ] **Step 1: Add batch UI and wiring to ScListView template**

Add after the `</AdvancedFilterBar>` line and before the `<ScTable>` line:

```html
<div v-if="selectedRows.length" style="margin-bottom:12px;display:flex;align-items:center;gap:12px;padding:8px 12px;background:#f0f9ff;border-radius:4px">
  <span style="font-size:13px;color:#1d4ed8;font-weight:500">{{ $t('batch.selected', { count: selectedRows.length }) }}</span>
  <el-button v-if="selectedRows.some(r => r.status === 'draft')" size="small" type="primary" @click="handleBatchSubmit">{{ $t('batch.submit') }}</el-button>
  <el-button v-if="selectedRows.some(r => r.status === 'manager_confirm')" size="small" type="primary" @click="handleBatchConfirm">{{ $t('batch.confirm') }}</el-button>
  <el-button v-if="selectedRows.some(r => r.status === 'pending')" size="small" type="success" @click="handleBatchApprove">{{ $t('batch.approve') }}</el-button>
</div>
```

Update `<ScTable>` to add `selectable` and `@selection-change`:

```html
<ScTable
  :rows="state.rows"
  :loading="state.loading"
  :empty-text="state.error || $t('sc.noRecords')"
  selectable
  @sort-change="handleSortChange"
  @row-click="row => $router.push(`/sc/${row.sc_id}`)"
  @selection-change="val => selectedRows = val"
/>
```

Add the progress modal just before `</template>`:

```html
<BatchProgressModal
  :visible="batchState.active"
  :title="batchTitle"
  :state="batchState"
  @abort="abort"
/>
```

- [ ] **Step 2: Add batch logic to ScListView script**

Add imports (merge with existing imports — add `callApi` if not present, add `useBatchAction`):

```javascript
import { useBatchAction } from '@/composables/useBatchAction.js'
import BatchProgressModal from '@/components/common/BatchProgressModal.vue'
import { ElMessageBox } from 'element-plus'
```

Add refs and composable setup (add after `const exporting = ref(false)`):

```javascript
const selectedRows = ref([])
const { state: batchState, runBatch, abort } = useBatchAction()
const batchTitle = ref('')
```

Add batch handler functions (add before `onMounted`):

```javascript
function showBatchResult(summary, actionName) {
  if (!summary) return
  let msg = `<p><strong>${t('batch.result', { action: t(`batch.${actionName}`) })}</strong></p>`
  msg += `<p style="color:#67c23a">${t('batch.success', { count: summary.succeeded })}</p>`
  msg += `<p style="color:#f56c6c">${t('batch.failed', { count: summary.failed })}</p>`
  if (summary.skipped) {
    msg += `<p style="color:#e6a23c">${t('batch.skipped', { count: summary.skipped })}</p>`
  }
  if (summary.failedItems.length) {
    msg += `<p><strong>${t('batch.failDetail')}:</strong></p><ul>`
    summary.failedItems.forEach(f => {
      msg += `<li>${f.id}: ${f.reason}</li>`
    })
    msg += '</ul>'
  }
  ElMessageBox.alert(msg, t('common.confirm'), {
    dangerouslyUseHTMLString: true,
    confirmButtonText: t('common.confirm')
  })
}

async function handleBatchSubmit() {
  batchTitle.value = t('batch.titleSubmit')
  const summary = await runBatch(selectedRows.value, 'submit', async (row) => {
    await callApi('submit_sc', { sc_id: row.sc_id, data: {} })
  }, t)
  if (summary) await searchScs()
  showBatchResult(summary, 'submit')
}

async function handleBatchConfirm() {
  batchTitle.value = t('batch.titleConfirm')
  const summary = await runBatch(selectedRows.value, 'confirm', async (row) => {
    await callApi('confirm_sc', { sc_id: row.sc_id })
  }, t)
  if (summary) await searchScs()
  showBatchResult(summary, 'confirm')
}

async function handleBatchApprove() {
  batchTitle.value = t('batch.titleApprove')
  const summary = await runBatch(selectedRows.value, 'approve', async (row) => {
    await callApi('approve_sc', { sc_id: row.sc_id, cascade_pos: false })
  }, t)
  if (summary) await searchScs()
  showBatchResult(summary, 'approve')
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/ScListView.vue
git commit -m "feat: add batch submit/confirm/approve to ScListView"
```

---

### Task 6: Wire batch operations into GrListView

**Files:**
- Modify: `frontend/src/views/GrListView.vue`

- [ ] **Step 1: Add batch UI and wiring to GrListView template**

Add after the button bar (`</div>` closing the export button div) and before `<el-table>`:

```html
<div v-if="selectedRows.length" style="margin-bottom:12px;display:flex;align-items:center;gap:12px;padding:8px 12px;background:#f0f9ff;border-radius:4px">
  <span style="font-size:13px;color:#1d4ed8;font-weight:500">{{ $t('batch.selected', { count: selectedRows.length }) }}</span>
  <el-button v-if="selectedRows.some(r => r.status === 'draft')" size="small" type="primary" @click="handleBatchSubmit">{{ $t('batch.submit') }}</el-button>
  <el-button v-if="selectedRows.some(r => r.status === 'manager_confirm')" size="small" type="primary" @click="handleBatchConfirm">{{ $t('batch.confirm') }}</el-button>
</div>
```

Add `type="selection"` column as the first `<el-table-column>` in the `<el-table>`:

```html
<el-table-column type="selection" width="50" />
```

Add `@selection-change` to `<el-table>`:

```html
<el-table :data="state.rows" v-loading="state.loading" stripe border @row-click="handleRowClick" @selection-change="val => selectedRows = val">
```

Add the progress modal just before `</template>`:

```html
<BatchProgressModal
  :visible="batchState.active"
  :title="batchTitle"
  :state="batchState"
  @abort="abort"
/>
```

- [ ] **Step 2: Add batch logic to GrListView script**

Add imports (merge into existing import block):

```javascript
import { useBatchAction } from '@/composables/useBatchAction.js'
import BatchProgressModal from '@/components/common/BatchProgressModal.vue'
import { ElMessageBox } from 'element-plus'
```

Add refs and composable setup (add after `const exporting = ref(false)`):

```javascript
const selectedRows = ref([])
const { state: batchState, runBatch, abort } = useBatchAction()
const batchTitle = ref('')
```

Add batch handler functions (add before `onMounted`):

```javascript
function showBatchResult(summary, actionName) {
  if (!summary) return
  let msg = `<p><strong>${t('batch.result', { action: t(`batch.${actionName}`) })}</strong></p>`
  msg += `<p style="color:#67c23a">${t('batch.success', { count: summary.succeeded })}</p>`
  msg += `<p style="color:#f56c6c">${t('batch.failed', { count: summary.failed })}</p>`
  if (summary.skipped) {
    msg += `<p style="color:#e6a23c">${t('batch.skipped', { count: summary.skipped })}</p>`
  }
  if (summary.failedItems.length) {
    msg += `<p><strong>${t('batch.failDetail')}:</strong></p><ul>`
    summary.failedItems.forEach(f => {
      msg += `<li>${f.id}: ${f.reason}</li>`
    })
    msg += '</ul>'
  }
  ElMessageBox.alert(msg, t('common.confirm'), {
    dangerouslyUseHTMLString: true,
    confirmButtonText: t('common.confirm')
  })
}

async function handleBatchSubmit() {
  batchTitle.value = t('batch.titleSubmit')
  const summary = await runBatch(selectedRows.value, 'submit', async (row) => {
    await callApi('submit_gr', { gr_id: row.gr_id })
  }, t)
  if (summary) await searchGrs()
  showBatchResult(summary, 'submit')
}

async function handleBatchConfirm() {
  batchTitle.value = t('batch.titleConfirm')
  const summary = await runBatch(selectedRows.value, 'confirm', async (row) => {
    await callApi('confirm_gr', { gr_id: row.gr_id })
  }, t)
  if (summary) await searchGrs()
  showBatchResult(summary, 'confirm')
}
```

Note: `ElMessageBox` is added to imports but `ElMessage` is already imported. Both are from `element-plus`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/GrListView.vue
git commit -m "feat: add batch submit/confirm to GrListView"
```

---

### Task 7: Build and verify

- [ ] **Step 1: Run frontend build**

```bash
cd frontend && npx vite build
```

Expected: build succeeds with no errors.

- [ ] **Step 2: Run backend tests**

```bash
uv run pytest tests/ -q
```

Expected: all 229 tests pass (no backend changes).

- [ ] **Step 3: Commit any build output changes**

```bash
cd ..
git add sc_gr_app/web/
git commit -m "chore: update built frontend assets for batch operations"
```
