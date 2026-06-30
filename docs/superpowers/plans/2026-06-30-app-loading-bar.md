# App-wide Loading Bar + Action Debounce Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a global loading bar that auto-appears for every `callApi` request, and disable action buttons during API calls to prevent double-clicks.

**Architecture:** Reactive `loadingState.count` in `bridge.js` auto-increments on every API call. `AppLoadingBar.vue` reads this count to show/hide a fixed 2px animated bar with CSS transition anti-flash. Detail/list views import `loadingState` and bind `:disabled="loadingState.count > 0"` on action buttons.

**Tech Stack:** Vue 3 + Element Plus + CSS animation

---

### Task 1: Add reactive loadingState to bridge.js

**Files:**
- Modify: `frontend/src/api/bridge.js`

- [ ] **Step 1: Add reactive import and export loadingState**

Edit `frontend/src/api/bridge.js`:

**Change 1 — add `import { reactive } from 'vue'` after the `ApiError` class:**

Old:
```js
class ApiError extends Error {
```

New:
```js
import { reactive } from 'vue'

class ApiError extends Error {
```

**Change 2 — add `loadingState` export before `callApi`:**

Old:
```js
const DEV_MODE = window.location.protocol === 'http:'

export async function callApi(method, payload = {}) {
```

New:
```js
const DEV_MODE = window.location.protocol === 'http:'

export const loadingState = reactive({ count: 0 })

export async function callApi(method, payload = {}) {
```

**Change 3 — wrap `callApi` body with count increment/decrement:**

Old:
```js
export async function callApi(method, payload = {}) {
  let result
  if (DEV_MODE) {
    if (!window.pywebview?.api) {
      throw new ApiError({ code: 'DEV_NO_BRIDGE', message: 'Dev mode: no pywebview bridge. Run in the desktop app.' })
    }
    result = await window.pywebview.api[method](payload)
  } else {
    result = await window.pywebview.api[method](payload)
  }
  if (!result.ok) {
    throw new ApiError(result.error)
  }
  return result.data
}
```

New:
```js
export async function callApi(method, payload = {}) {
  loadingState.count++
  try {
    let result
    if (DEV_MODE) {
      if (!window.pywebview?.api) {
        throw new ApiError({ code: 'DEV_NO_BRIDGE', message: 'Dev mode: no pywebview bridge. Run in the desktop app.' })
      }
      result = await window.pywebview.api[method](payload)
    } else {
      result = await window.pywebview.api[method](payload)
    }
    if (!result.ok) {
      throw new ApiError(result.error)
    }
    return result.data
  } finally {
    loadingState.count--
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/bridge.js
git commit -m "feat: add reactive loadingState counter to callApi bridge"
```

---

### Task 2: Create AppLoadingBar component

**Files:**
- Create: `frontend/src/components/common/AppLoadingBar.vue`

- [ ] **Step 1: Create the component file**

Write `frontend/src/components/common/AppLoadingBar.vue`:

```vue
<template>
  <Transition name="loading-bar">
    <div v-if="loadingState.count > 0" class="app-loading-bar" />
  </Transition>
</template>

<script setup>
import { loadingState } from '@/api/bridge.js'
</script>

<style scoped>
.app-loading-bar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  z-index: 9999;
  pointer-events: none;
}

.app-loading-bar::after {
  content: '';
  display: block;
  height: 100%;
  width: 100%;
  background: linear-gradient(90deg, transparent, #409eff, transparent);
  animation: loading-slide 1.2s ease-in-out infinite;
}

@keyframes loading-slide {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

.loading-bar-enter-active {
  transition: opacity 0.1s ease 0.1s;
}
.loading-bar-leave-active {
  transition: opacity 0.15s ease;
}
.loading-bar-enter-from,
.loading-bar-leave-to {
  opacity: 0;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/common/AppLoadingBar.vue
git commit -m "feat: add AppLoadingBar component with CSS transition anti-flash"
```

---

### Task 3: Mount AppLoadingBar in App.vue

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Add AppLoadingBar above router-view**

Edit `frontend/src/App.vue`:

**Change 1 — add import:**

Old:
```js
import LoginView from '@/views/LoginView.vue'
```

New:
```js
import LoginView from '@/views/LoginView.vue'
import AppLoadingBar from '@/components/common/AppLoadingBar.vue'
```

**Change 2 — add component before router-view in both layouts:**

Old:
```vue
<template>
  <LoginView v-if="layout === 'standalone'" />
  <el-container v-else class="app-shell">
    <el-aside :width="sidebarCollapsed ? '64px' : '210px'" class="app-sidebar">
      <SideNav :collapsed="sidebarCollapsed" @toggle="sidebarCollapsed = !sidebarCollapsed" />
    </el-aside>
    <el-container>
      <el-header height="56px" class="app-header">
        <AppHeader />
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>
```

New:
```vue
<template>
  <AppLoadingBar />
  <LoginView v-if="layout === 'standalone'" />
  <el-container v-else class="app-shell">
    <el-aside :width="sidebarCollapsed ? '64px' : '210px'" class="app-sidebar">
      <SideNav :collapsed="sidebarCollapsed" @toggle="sidebarCollapsed = !sidebarCollapsed" />
    </el-aside>
    <el-container>
      <el-header height="56px" class="app-header">
        <AppHeader />
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/App.vue
git commit -m "feat: mount AppLoadingBar in App.vue"
```

---

### Task 4: Add :disabled to ScDetailView action buttons

**Files:**
- Modify: `frontend/src/views/ScDetailView.vue`

- [ ] **Step 1: Import loadingState**

Edit `frontend/src/views/ScDetailView.vue` — add import after the existing `callApi` import:

Old:
```js
import { callApi } from '@/api/bridge.js'
```

New:
```js
import { callApi, loadingState } from '@/api/bridge.js'
```

- [ ] **Step 2: Add :disabled to header action buttons**

Each button in the `.header-actions` div gets `:disabled="loadingState.count > 0"`:

Old:
```vue
      <div class="header-actions">
        <el-button v-if="permissions.can_edit_sc" @click="openEditDialog">{{ $t('common.edit') }}</el-button>
        <el-button v-if="permissions.can_submit_sc" type="primary" @click="handleSubmit">{{ $t('common.submit') }}</el-button>
        <el-button v-if="permissions.can_confirm_sc" type="primary" @click="handleConfirm">{{ $t('sc.confirm') }}</el-button>
        <el-button v-if="permissions.can_approve_sc" type="success" @click="handleApprove">{{ $t('common.approve') }}</el-button>
        <el-button v-if="permissions.can_deny_sc" type="warning" @click="handleDeny">{{ $t('common.deny') }}</el-button>
        <el-button v-if="permissions.can_recall_sc" type="warning" @click="handleRecall">{{ $t('sc.recall') }}</el-button>
        <el-button v-if="permissions.can_delete_sc" type="danger" @click="handleDelete">{{ $t('common.delete') }}</el-button>
        <el-button v-if="permissions.can_finish_sc" type="danger" @click="handleFinish">{{ $t('common.finish') }}</el-button>
        <el-button v-if="permissions.can_transfer_sc" @click="openTransferDialog">{{ $t('sc.transferOwner') }}</el-button>
      </div>
```

New:
```vue
      <div class="header-actions">
        <el-button v-if="permissions.can_edit_sc" :disabled="loadingState.count > 0" @click="openEditDialog">{{ $t('common.edit') }}</el-button>
        <el-button v-if="permissions.can_submit_sc" type="primary" :disabled="loadingState.count > 0" @click="handleSubmit">{{ $t('common.submit') }}</el-button>
        <el-button v-if="permissions.can_confirm_sc" type="primary" :disabled="loadingState.count > 0" @click="handleConfirm">{{ $t('sc.confirm') }}</el-button>
        <el-button v-if="permissions.can_approve_sc" type="success" :disabled="loadingState.count > 0" @click="handleApprove">{{ $t('common.approve') }}</el-button>
        <el-button v-if="permissions.can_deny_sc" type="warning" :disabled="loadingState.count > 0" @click="handleDeny">{{ $t('common.deny') }}</el-button>
        <el-button v-if="permissions.can_recall_sc" type="warning" :disabled="loadingState.count > 0" @click="handleRecall">{{ $t('sc.recall') }}</el-button>
        <el-button v-if="permissions.can_delete_sc" type="danger" :disabled="loadingState.count > 0" @click="handleDelete">{{ $t('common.delete') }}</el-button>
        <el-button v-if="permissions.can_finish_sc" type="danger" :disabled="loadingState.count > 0" @click="handleFinish">{{ $t('common.finish') }}</el-button>
        <el-button v-if="permissions.can_transfer_sc" :disabled="loadingState.count > 0" @click="openTransferDialog">{{ $t('sc.transferOwner') }}</el-button>
      </div>
```

- [ ] **Step 3: Add :disabled to Add PO button**

Old:
```vue
          <el-button
            v-if="permissions.can_manage_po && (detail.sc?.status === 'approved' || detail.sc?.status === 'finished')"
            type="primary" size="small"
            @click="poDialogVisible = true; poDialogMode = 'create'; poDialogRecord = null"
          >
```

New:
```vue
          <el-button
            v-if="permissions.can_manage_po && (detail.sc?.status === 'approved' || detail.sc?.status === 'finished')"
            type="primary" size="small"
            :disabled="loadingState.count > 0"
            @click="poDialogVisible = true; poDialogMode = 'create'; poDialogRecord = null"
          >
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/ScDetailView.vue
git commit -m "feat: add :disabled to ScDetailView action buttons during API calls"
```

---

### Task 5: Add :disabled to ScVendorSection add/remove buttons

**Files:**
- Modify: `frontend/src/components/sc/ScVendorSection.vue`

- [ ] **Step 1: Import loadingState**

Edit `frontend/src/components/sc/ScVendorSection.vue` — add import in `<script setup>`:

Old:
```js
import { ref, computed } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import VendorPickerDialog from './VendorPickerDialog.vue'
```

New:
```js
import { ref, computed } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import VendorPickerDialog from './VendorPickerDialog.vue'
import { loadingState } from '@/api/bridge.js'
```

- [ ] **Step 2: Add :disabled to Add Vendor button**

Old:
```vue
      <el-button v-if="canManage" type="primary" size="small" @click="pickerVisible = true">
```

New:
```vue
      <el-button v-if="canManage" type="primary" size="small" :disabled="loadingState.count > 0" @click="pickerVisible = true">
```

- [ ] **Step 3: Add :disabled to Remove Vendor popconfirm button**

Old:
```vue
            <el-button type="danger" link size="small" style="margin-left:8px;flex-shrink:0">
```

New:
```vue
            <el-button type="danger" link size="small" :disabled="loadingState.count > 0" style="margin-left:8px;flex-shrink:0">
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/sc/ScVendorSection.vue
git commit -m "feat: add :disabled to ScVendorSection buttons during API calls"
```

---

### Task 6: Add :disabled to PoDetailView action buttons

**Files:**
- Modify: `frontend/src/views/PoDetailView.vue`

- [ ] **Step 1: Import loadingState**

Old:
```js
import { callApi } from '@/api/bridge.js'
```

New:
```js
import { callApi, loadingState } from '@/api/bridge.js'
```

- [ ] **Step 2: Add :disabled to header action buttons**

Old:
```vue
      <div class="header-actions">
        <el-button v-if="scDetail?.permissions?.can_manage_po && po.status !== 'finished'" @click="openEditDialog">{{ $t('common.edit') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_po && po.status === 'draft'" type="primary" @click="handleSubmit">{{ $t('common.submit') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_po && po.status === 'activing'" type="info" @click="handleFinish">{{ $t('common.finish') }}</el-button>
        <el-button v-if="isRequester && po.status === 'activing'" type="warning" @click="handleRecall">{{ $t('po.recall') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_delete_po && po.status === 'draft'" type="danger" @click="handleDelete">{{ $t('common.delete') }}</el-button>
      </div>
```

New:
```vue
      <div class="header-actions">
        <el-button v-if="scDetail?.permissions?.can_manage_po && po.status !== 'finished'" :disabled="loadingState.count > 0" @click="openEditDialog">{{ $t('common.edit') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_po && po.status === 'draft'" type="primary" :disabled="loadingState.count > 0" @click="handleSubmit">{{ $t('common.submit') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_po && po.status === 'activing'" type="info" :disabled="loadingState.count > 0" @click="handleFinish">{{ $t('common.finish') }}</el-button>
        <el-button v-if="isRequester && po.status === 'activing'" type="warning" :disabled="loadingState.count > 0" @click="handleRecall">{{ $t('po.recall') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_delete_po && po.status === 'draft'" type="danger" :disabled="loadingState.count > 0" @click="handleDelete">{{ $t('common.delete') }}</el-button>
      </div>
```

- [ ] **Step 3: Add :disabled to Add GR button**

Old:
```vue
          <el-button v-if="scDetail?.permissions?.can_manage_gr" type="primary" size="small" @click="grDialogVisible = true; grDialogMode = 'create'; grDialogRecord = null">
```

New:
```vue
          <el-button v-if="scDetail?.permissions?.can_manage_gr" type="primary" size="small" :disabled="loadingState.count > 0" @click="grDialogVisible = true; grDialogMode = 'create'; grDialogRecord = null">
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/PoDetailView.vue
git commit -m "feat: add :disabled to PoDetailView action buttons during API calls"
```

---

### Task 7: Add :disabled to PoTable action buttons

**Files:**
- Modify: `frontend/src/components/po/PoTable.vue`

- [ ] **Step 1: Import loadingState**

Old:
```js
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'
```

New:
```js
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'
import { loadingState } from '@/api/bridge.js'
```

- [ ] **Step 2: Add :disabled to PoTable action buttons**

Old:
```vue
        <el-button type="primary" link size="small" @click.stop="$emit('detail', row)">{{ $t('common.detail') }}</el-button>
        <el-button type="primary" link size="small" @click.stop="$emit('edit', row)">{{ $t('po.edit') }}</el-button>
        <el-button v-if="row.status === 'draft'" type="primary" link size="small" @click.stop="$emit('submit', row)">{{ $t('common.submit') }}</el-button>
        <el-button v-if="row.status === 'activing'" type="info" link size="small" @click.stop="$emit('finish', row)">{{ $t('po.finish') }}</el-button>
```

New:
```vue
        <el-button type="primary" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('detail', row)">{{ $t('common.detail') }}</el-button>
        <el-button type="primary" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('edit', row)">{{ $t('po.edit') }}</el-button>
        <el-button v-if="row.status === 'draft'" type="primary" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('submit', row)">{{ $t('common.submit') }}</el-button>
        <el-button v-if="row.status === 'activing'" type="info" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('finish', row)">{{ $t('po.finish') }}</el-button>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/po/PoTable.vue
git commit -m "feat: add :disabled to PoTable action buttons during API calls"
```

---

### Task 8: Add :disabled to GrDetailView action buttons

**Files:**
- Modify: `frontend/src/views/GrDetailView.vue`

- [ ] **Step 1: Import loadingState**

Old:
```js
import { callApi } from '@/api/bridge.js'
```

New:
```js
import { callApi, loadingState } from '@/api/bridge.js'
```

- [ ] **Step 2: Add :disabled to header action buttons**

Old:
```vue
      <div class="header-actions">
        <el-button v-if="scDetail?.permissions?.can_manage_gr && ['draft','pending','manager_confirm','approved'].includes(gr.status)" @click="openEditDialog">{{ $t('common.edit') }}</el-button>
        <el-button v-if="scDetail?.permissions?.is_admin && gr.status === 'manager_confirm'" type="primary" @click="handleConfirm">{{ $t('gr.confirm') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_gr && gr.status === 'pending'" type="success" @click="handleApprove">{{ $t('common.approve') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_gr && gr.status === 'pending'" type="danger" @click="handleDeny">{{ $t('gr.deny') }}</el-button>
        <el-button v-if="isRequester && (gr.status === 'manager_confirm' || gr.status === 'pending')" type="warning" @click="handleRecall">{{ $t('gr.recall') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_delete_gr && gr.status === 'draft'" type="danger" @click="handleDelete">{{ $t('common.delete') }}</el-button>
      </div>
```

New:
```vue
      <div class="header-actions">
        <el-button v-if="scDetail?.permissions?.can_manage_gr && ['draft','pending','manager_confirm','approved'].includes(gr.status)" :disabled="loadingState.count > 0" @click="openEditDialog">{{ $t('common.edit') }}</el-button>
        <el-button v-if="scDetail?.permissions?.is_admin && gr.status === 'manager_confirm'" type="primary" :disabled="loadingState.count > 0" @click="handleConfirm">{{ $t('gr.confirm') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_gr && gr.status === 'pending'" type="success" :disabled="loadingState.count > 0" @click="handleApprove">{{ $t('common.approve') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_gr && gr.status === 'pending'" type="danger" :disabled="loadingState.count > 0" @click="handleDeny">{{ $t('gr.deny') }}</el-button>
        <el-button v-if="isRequester && (gr.status === 'manager_confirm' || gr.status === 'pending')" type="warning" :disabled="loadingState.count > 0" @click="handleRecall">{{ $t('gr.recall') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_delete_gr && gr.status === 'draft'" type="danger" :disabled="loadingState.count > 0" @click="handleDelete">{{ $t('common.delete') }}</el-button>
      </div>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/GrDetailView.vue
git commit -m "feat: add :disabled to GrDetailView action buttons during API calls"
```

---

### Task 9: Add :disabled to GrTable action buttons

**Files:**
- Modify: `frontend/src/components/po/GrTable.vue`

- [ ] **Step 1: Import loadingState**

Old:
```js
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'
```

New:
```js
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'
import { loadingState } from '@/api/bridge.js'
```

- [ ] **Step 2: Add :disabled to GrTable action buttons**

Old:
```vue
        <el-button type="primary" link size="small" @click.stop="$emit('detail', row)">{{ $t('common.detail') }}</el-button>
        <el-button type="primary" link size="small" @click.stop="$emit('edit', row)">{{ $t('gr.edit') }}</el-button>
        <el-button v-if="row.status === 'draft'" type="primary" link size="small" @click.stop="$emit('submit', row)">{{ $t('common.submit') }}</el-button>
        <el-button v-if="row.status === 'pending'" type="success" link size="small" @click.stop="$emit('approve', row)">{{ $t('gr.approve') }}</el-button>
        <el-popconfirm v-if="row.status === 'pending'" :title="$t('gr.denyConfirm')" @confirm="$emit('deny', row)">
          <template #reference>
            <el-button type="danger" link size="small" @click.stop>{{ $t('gr.deny') }}</el-button>
          </template>
        </el-popconfirm>
        <el-button type="info" link size="small" @click.stop="$emit('attachments', row)">
```

New:
```vue
        <el-button type="primary" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('detail', row)">{{ $t('common.detail') }}</el-button>
        <el-button type="primary" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('edit', row)">{{ $t('gr.edit') }}</el-button>
        <el-button v-if="row.status === 'draft'" type="primary" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('submit', row)">{{ $t('common.submit') }}</el-button>
        <el-button v-if="row.status === 'pending'" type="success" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('approve', row)">{{ $t('gr.approve') }}</el-button>
        <el-popconfirm v-if="row.status === 'pending'" :title="$t('gr.denyConfirm')" @confirm="$emit('deny', row)">
          <template #reference>
            <el-button type="danger" link size="small" :disabled="loadingState.count > 0" @click.stop>{{ $t('gr.deny') }}</el-button>
          </template>
        </el-popconfirm>
        <el-button type="info" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('attachments', row)">
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/po/GrTable.vue
git commit -m "feat: add :disabled to GrTable action buttons during API calls"
```

---

### Task 10: Add :disabled to ScListView New SC / Import buttons

**Files:**
- Modify: `frontend/src/views/ScListView.vue`

- [ ] **Step 1: Import loadingState**

Old:
```js
import { callApi } from '@/api/bridge.js'
```

New:
```js
import { callApi, loadingState } from '@/api/bridge.js'
```

- [ ] **Step 2: Add :disabled to New SC, Import, Template, and batch buttons**

Old:
```vue
        <el-button type="primary" @click="scDialogVisible = true; scDialogMode = 'create'">
          <el-icon><Plus /></el-icon> {{ $t('sc.newSc') }}
        </el-button>
        <el-button @click="importVisible = true">
          <el-icon><Upload /></el-icon> Import
        </el-button>
        <el-button @click="downloadTemplate">
          <el-icon><Download /></el-icon> Template
        </el-button>
```

New:
```vue
        <el-button type="primary" :disabled="loadingState.count > 0" @click="scDialogVisible = true; scDialogMode = 'create'">
          <el-icon><Plus /></el-icon> {{ $t('sc.newSc') }}
        </el-button>
        <el-button :disabled="loadingState.count > 0" @click="importVisible = true">
          <el-icon><Upload /></el-icon> Import
        </el-button>
        <el-button :disabled="loadingState.count > 0" @click="downloadTemplate">
          <el-icon><Download /></el-icon> Template
        </el-button>
```

- [ ] **Step 3: Add :disabled to batch action buttons**

Old:
```vue
      <el-button v-if="selectedRows.some(r => r.status === 'draft')" size="small" type="primary" @click="handleBatchSubmit">{{ $t('batch.submit') }}</el-button>
      <el-button v-if="isAdmin && selectedRows.some(r => r.status === 'manager_confirm')" size="small" type="primary" @click="handleBatchConfirm">{{ $t('batch.confirm') }}</el-button>
      <el-button v-if="isAdmin && selectedRows.some(r => r.status === 'pending')" size="small" type="success" @click="handleBatchApprove">{{ $t('batch.approve') }}</el-button>
```

New:
```vue
      <el-button v-if="selectedRows.some(r => r.status === 'draft')" size="small" type="primary" :disabled="loadingState.count > 0" @click="handleBatchSubmit">{{ $t('batch.submit') }}</el-button>
      <el-button v-if="isAdmin && selectedRows.some(r => r.status === 'manager_confirm')" size="small" type="primary" :disabled="loadingState.count > 0" @click="handleBatchConfirm">{{ $t('batch.confirm') }}</el-button>
      <el-button v-if="isAdmin && selectedRows.some(r => r.status === 'pending')" size="small" type="success" :disabled="loadingState.count > 0" @click="handleBatchApprove">{{ $t('batch.approve') }}</el-button>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/ScListView.vue
git commit -m "feat: add :disabled to ScListView action buttons during API calls"
```

---

### Task 11: Build and verify

- [ ] **Step 1: Build the frontend**

```bash
cd frontend && npm run build
```

Expected: Build succeeds with no errors.

- [ ] **Step 2: Copy built assets to web directory**

```bash
cp -r frontend/dist/* sc_gr_app/web/assets/
```

(Check the actual build output path if different.)

- [ ] **Step 3: Manual verification checklist**

Start the app and verify each item:

1. Navigate to SC detail → click **Approve** → verify:
   - Top loading bar appears (blue sliding gradient, 2px)
   - All header buttons become disabled (grayed out)
   - Bar disappears when operation completes (success or error message shows)
2. Navigate to PO detail → click **Finish** → verify same behavior
3. Navigate to GR detail → click **Approve** → verify same behavior
4. Verify fast operations (navigating between views, `list_users` calls) do NOT flash the bar
5. Open SC form dialog → verify submit button still has its own `:loading` spinner and works correctly
6. Verify search queries still show table `v-loading` correctly

- [ ] **Step 4: Commit any build artifacts**

```bash
git add sc_gr_app/web/assets/
git commit -m "build: update web assets with loading bar feature"
```
