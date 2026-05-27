# Frontend Vue + Element Plus Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete rewrite of frontend from vanilla JS/PicoCSS/Alpine.js to Vue 3 + Element Plus, retaining the pywebview JS Bridge communication model.

**Architecture:** Independent `frontend/` Vue 3 SPA with Vite 6, Element Plus 2.11, Vue Router 4 (hash history). Build output to `sc_gr_app/web/`. All forms use el-dialog. SC → PO → GR use separate detail pages with breadcrumb navigation. Sidebar + header layout, no global search.

**Tech Stack:** Vue 3.5, Element Plus 2.11, Vite 6, Vue Router 4, @element-plus/icons-vue, Python 3.11, pywebview, pystray

---

## File Structure

```
frontend/                              # NEW — independent frontend project
├── package.json
├── vite.config.js
├── index.html
└── src/
    ├── main.js
    ├── App.vue
    ├── assets/
    │   └── main.css
    ├── api/
    │   └── bridge.js
    ├── composables/
    │   ├── useUser.js
    │   ├── useSc.js
    │   ├── usePo.js
    │   ├── useGr.js
    │   ├── useVendor.js
    │   └── useLogs.js
    ├── router/
    │   └── index.js
    ├── components/
    │   ├── layout/
    │   │   ├── SideNav.vue
    │   │   └── AppHeader.vue
    │   ├── common/
    │   │   ├── StatusBadge.vue
    │   │   ├── AmountDisplay.vue
    │   │   └── FilterBar.vue
    │   ├── sc/
    │   │   ├── ScTable.vue
    │   │   ├── ScDetailCard.vue
    │   │   └── ScFormDialog.vue
    │   ├── po/
    │   │   ├── PoTable.vue
    │   │   ├── PoFormDialog.vue
    │   │   ├── GrTable.vue
    │   │   └── GrFormDialog.vue
    │   ├── vendor/
    │   │   └── VendorFormDialog.vue
    │   └── system/
    │       └── UserFormDialog.vue
    └── views/
        ├── LoginView.vue
        ├── HomeView.vue
        ├── ScListView.vue
        ├── ScDetailView.vue
        ├── PoDetailView.vue
        ├── PoListView.vue
        ├── GrListView.vue
        ├── VendorListView.vue
        ├── LogsView.vue
        └── SystemView.vue

sc_gr_app/
├── __init__.py                         # MODIFY — add __version__
├── app_shell.py                        # REWRITE — WebView2, dev mode, tray, mutex
├── api/
│   └── bridge.py                       # MODIFY — add vendor CRUD + enable_user
├── services/
│   ├── vendor_service.py               # MODIFY — add update_vendor, disable_vendor
│   └── user_service.py                 # MODIFY — add enable_user
└── web/                                # CLEAN — old files removed after build validation
```

---

### Task 1: Scaffold frontend project

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.js`

- [ ] **Step 1: Create frontend/package.json**

```json
{
  "name": "sc-gr-management-frontend",
  "version": "2.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vue": "^3.5.13",
    "vue-router": "^4.5.0",
    "element-plus": "^2.11.0",
    "@element-plus/icons-vue": "^2.3.1"
  },
  "devDependencies": {
    "vite": "^6.0.0",
    "@vitejs/plugin-vue": "^5.2.0"
  }
}
```

- [ ] **Step 2: Create frontend/vite.config.js**

```js
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: './',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  build: {
    outDir: '../sc_gr_app/web',
    emptyOutDir: true
  },
  server: {
    port: 5173
  }
})
```

- [ ] **Step 3: Create frontend/index.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SC GR Management</title>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.js"></script>
</body>
</html>
```

- [ ] **Step 4: Create frontend/src/main.js**

```js
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'
import './assets/main.css'

const app = createApp(App)
app.use(ElementPlus, { size: 'default' })
app.use(router)
app.mount('#app')
```

- [ ] **Step 5: Install dependencies and verify dev server starts**

```bash
cd frontend && npm install && npm run dev
```

Expected: Vite dev server starts on http://localhost:5173 (blank page).

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/vite.config.js frontend/index.html frontend/src/main.js
git commit -m "feat: scaffold Vue 3 + Element Plus frontend project"
```

---

### Task 2: Bridge layer + router + App.vue skeleton

**Files:**
- Create: `frontend/src/api/bridge.js`
- Create: `frontend/src/router/index.js`
- Create: `frontend/src/App.vue`

- [ ] **Step 1: Create frontend/src/api/bridge.js**

```js
class ApiError extends Error {
  constructor(error) {
    super(error.message || 'API error')
    this.code = error.code || 'UNKNOWN'
  }
}

const DEV_MODE = window.location.protocol === 'http:'

export async function callApi(method, payload = {}) {
  let result
  if (DEV_MODE) {
    // In dev, pywebview.api is unavailable — use mock data or throw with hint
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

export { ApiError }
```

- [ ] **Step 2: Create frontend/src/router/index.js**

```js
import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { layout: 'standalone' }
  },
  {
    path: '/workbench',
    name: 'workbench',
    component: () => import('@/views/HomeView.vue'),
    meta: { layout: 'default', title: 'Workbench' }
  },
  {
    path: '/sc',
    name: 'sc-list',
    component: () => import('@/views/ScListView.vue'),
    meta: { layout: 'default', title: 'SC List' }
  },
  {
    path: '/sc/:id',
    name: 'sc-detail',
    component: () => import('@/views/ScDetailView.vue'),
    meta: { layout: 'default', title: 'SC Detail' }
  },
  {
    path: '/sc/:scId/po/:poId',
    name: 'po-detail',
    component: () => import('@/views/PoDetailView.vue'),
    meta: { layout: 'default', title: 'PO Detail' }
  },
  {
    path: '/po',
    name: 'po-list',
    component: () => import('@/views/PoListView.vue'),
    meta: { layout: 'default', title: 'PO List' }
  },
  {
    path: '/gr',
    name: 'gr-list',
    component: () => import('@/views/GrListView.vue'),
    meta: { layout: 'default', title: 'GR List' }
  },
  {
    path: '/vendor',
    name: 'vendor-list',
    component: () => import('@/views/VendorListView.vue'),
    meta: { layout: 'default', title: 'Vendor List' }
  },
  {
    path: '/logs',
    name: 'logs',
    component: () => import('@/views/LogsView.vue'),
    meta: { layout: 'default', title: 'Audit Logs' }
  },
  {
    path: '/system',
    name: 'system',
    component: () => import('@/views/SystemView.vue'),
    meta: { layout: 'default', title: 'System' }
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/login'
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

router.beforeEach(async (to, from, next) => {
  // Allow login page unconditionally
  if (to.name === 'login') return next()

  // Verify auth before any other route
  try {
    const { callApi } = await import('@/api/bridge.js')
    const user = await callApi('current_user')
    // Store user for components to access
    window.__currentUser = user
    next()
  } catch {
    // Not authenticated — redirect to login
    next({ name: 'login', query: { redirect: to.fullPath } })
  }
})

export default router
```

- [ ] **Step 3: Create frontend/src/App.vue**

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

<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import SideNav from '@/components/layout/SideNav.vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import LoginView from '@/views/LoginView.vue'

const route = useRoute()
const sidebarCollapsed = ref(false)

const layout = computed(() => route.meta?.layout || 'default')
</script>

<style scoped>
.app-shell {
  height: 100vh;
  overflow: hidden;
}
.app-sidebar {
  background: var(--sidebar-bg);
  transition: width 0.2s ease;
  overflow: hidden;
}
.app-header {
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  padding: 0 20px;
}
.app-main {
  background: #f1f5f9;
  overflow-y: auto;
  padding: 20px;
}
</style>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/bridge.js frontend/src/router/index.js frontend/src/App.vue
git commit -m "feat: add bridge layer, router with auth guard, App shell layout"
```

---

### Task 3: Shared components — StatusBadge, AmountDisplay, FilterBar

**Files:**
- Create: `frontend/src/components/common/StatusBadge.vue`
- Create: `frontend/src/components/common/AmountDisplay.vue`
- Create: `frontend/src/components/common/FilterBar.vue`

- [ ] **Step 1: Create StatusBadge.vue**

```vue
<template>
  <el-tag :type="tagType" size="small" :class="['status-badge', `status-row-${status}`]">
    {{ label }}
  </el-tag>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, required: true }
})

const STATUS_LABELS = {
  draft: 'Draft',
  pending: 'Pending',
  approved: 'Approved',
  denied: 'Denied',
  closed: 'Closed',
  po_pending: 'Pending',
  po_approved: 'Approved',
  finished: 'Finished',
  cancelled: 'Cancelled'
}

const STATUS_TYPES = {
  draft: '',
  pending: 'warning',
  approved: 'success',
  denied: 'danger',
  closed: 'info',
  po_pending: 'warning',
  po_approved: 'success',
  finished: 'info',
  cancelled: 'danger'
}

const tagType = computed(() => STATUS_TYPES[props.status] || 'info')
const label = computed(() => STATUS_LABELS[props.status] || props.status)
</script>
```

- [ ] **Step 2: Create AmountDisplay.vue**

```vue
<template>
  <span class="amount-display">{{ formatted }}</span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  value: { type: [Number, String], default: null }
})

const formatted = computed(() => {
  if (props.value == null || props.value === '') return '-'
  const num = Number(props.value)
  if (isNaN(num)) return String(props.value)
  return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
})
</script>

<style scoped>
.amount-display {
  font-variant-numeric: tabular-nums;
  text-align: right;
  display: inline-block;
}
</style>
```

- [ ] **Step 3: Create FilterBar.vue**

```vue
<template>
  <div class="filter-bar">
    <div class="filter-controls">
      <slot name="filters" />
      <el-button @click="$emit('reset')" :disabled="disabled">Reset</el-button>
    </div>
    <div class="filter-actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup>
defineProps({
  disabled: { type: Boolean, default: false }
})
defineEmits(['reset'])
</script>

<style scoped>
.filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #fff;
  border-radius: 4px;
  margin-bottom: 12px;
  gap: 12px;
}
.filter-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.filter-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
</style>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/common/StatusBadge.vue frontend/src/components/common/AmountDisplay.vue frontend/src/components/common/FilterBar.vue
git commit -m "feat: add shared components — StatusBadge, AmountDisplay, FilterBar"
```

---

### Task 4: Layout components — SideNav + AppHeader

**Files:**
- Create: `frontend/src/components/layout/SideNav.vue`
- Create: `frontend/src/components/layout/AppHeader.vue`

- [ ] **Step 1: Create SideNav.vue**

```vue
<template>
  <div class="sidenav-container">
    <div class="sidenav-brand">
      <span v-if="!collapsed" class="brand-text">SC GR Ops</span>
      <span v-else class="brand-icon">SC</span>
    </div>
    <el-menu
      :default-active="activeRoute"
      :collapse="collapsed"
      :router="true"
      background-color="transparent"
      text-color="#cbd5e1"
      active-text-color="#3b82f6"
      class="sidenav-menu"
    >
      <el-menu-item index="/workbench">
        <el-icon><Monitor /></el-icon>
        <span>Workbench</span>
      </el-menu-item>
      <el-menu-item index="/sc">
        <el-icon><Document /></el-icon>
        <span>SC</span>
      </el-menu-item>
      <el-menu-item index="/po">
        <el-icon><ShoppingCart /></el-icon>
        <span>PO</span>
      </el-menu-item>
      <el-menu-item index="/gr">
        <el-icon><CircleCheck /></el-icon>
        <span>GR</span>
      </el-menu-item>
      <el-menu-item index="/vendor">
        <el-icon><OfficeBuilding /></el-icon>
        <span>Vendor</span>
      </el-menu-item>
      <el-menu-item index="/logs">
        <el-icon><Notebook /></el-icon>
        <span>Logs</span>
      </el-menu-item>
      <el-menu-item v-if="isAdmin" index="/system">
        <el-icon><Setting /></el-icon>
        <span>System</span>
      </el-menu-item>
    </el-menu>
    <div class="sidenav-footer" @click="$emit('toggle')">
      <el-icon>
        <DArrowLeft v-if="!collapsed" />
        <DArrowRight v-else />
      </el-icon>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  Monitor, Document, ShoppingCart, CircleCheck, OfficeBuilding,
  Notebook, Setting, DArrowLeft, DArrowRight
} from '@element-plus/icons-vue'

defineProps({
  collapsed: { type: Boolean, default: false }
})
defineEmits(['toggle'])

const route = useRoute()

const activeRoute = computed(() => {
  if (route.path.startsWith('/sc')) return '/sc'
  if (route.path.startsWith('/po')) return '/po'
  if (route.path.startsWith('/gr')) return '/gr'
  return route.path
})

const isAdmin = computed(() => window.__currentUser?.role === 'admin')
</script>

<style scoped>
.sidenav-container {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.sidenav-brand {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-weight: 700;
  font-size: 16px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}
.brand-icon { font-size: 18px; }
.sidenav-menu {
  flex: 1;
  border-right: none;
}
.sidenav-menu .el-menu-item {
  border-left: 3px solid transparent;
}
.sidenav-menu .el-menu-item.is-active {
  border-left-color: #3b82f6;
  background: rgba(59,130,246,0.12);
}
.sidenav-footer {
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  cursor: pointer;
  border-top: 1px solid rgba(255,255,255,0.08);
}
.sidenav-footer:hover { color: #cbd5e1; }
</style>
```

- [ ] **Step 2: Create AppHeader.vue**

```vue
<template>
  <div class="header-left">
    <span class="header-title">SC GR Operations</span>
    <el-breadcrumb separator="/">
      <el-breadcrumb-item :to="{ path: '/workbench' }">Workbench</el-breadcrumb-item>
      <el-breadcrumb-item v-if="routeName === 'sc-list'">SC List</el-breadcrumb-item>
      <el-breadcrumb-item v-if="routeName === 'sc-detail'">
        <router-link :to="{ path: '/sc' }">SC List</router-link>
      </el-breadcrumb-item>
      <el-breadcrumb-item v-if="routeName === 'sc-detail'">SC Detail</el-breadcrumb-item>
      <el-breadcrumb-item v-if="routeName === 'po-detail'">
        <router-link :to="{ path: '/sc' }">SC List</router-link>
      </el-breadcrumb-item>
      <el-breadcrumb-item v-if="routeName === 'po-detail'">
        <router-link :to="{ path: `/sc/${$route.params.scId}` }">SC Detail</router-link>
      </el-breadcrumb-item>
      <el-breadcrumb-item v-if="routeName === 'po-detail'">PO Detail</el-breadcrumb-item>
    </el-breadcrumb>
  </div>
  <div class="header-right">
    <el-dropdown trigger="click">
      <span class="user-info">
        {{ user?.user_name || 'User' }}
        <el-tag size="small" :type="user?.role === 'admin' ? 'danger' : ''">{{ user?.role }}</el-tag>
      </span>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item @click="handleLogout">Exit</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const routeName = computed(() => route.name)
const user = computed(() => window.__currentUser || null)

function handleLogout() {
  window.__currentUser = null
  router.push('/login')
}
</script>

<style scoped>
.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
  flex: 1;
}
.header-title {
  font-weight: 700;
  font-size: 15px;
  color: #1e293b;
}
.header-right {
  display: flex;
  align-items: center;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: #475569;
  font-size: 14px;
}
</style>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/layout/SideNav.vue frontend/src/components/layout/AppHeader.vue
git commit -m "feat: add layout components — SideNav, AppHeader with breadcrumbs"
```

---

### Task 5: Login view + CSS theme variables

**Files:**
- Create: `frontend/src/assets/main.css`
- Create: `frontend/src/views/LoginView.vue`

- [ ] **Step 1: Create frontend/src/assets/main.css**

```css
:root {
  --el-border-radius-base: 4px;
  --el-border-radius-small: 2px;
  --sidebar-bg: #1e293b;
  --sidebar-text: #cbd5e1;
  --sidebar-active: #3b82f6;
  --header-height: 56px;
  --table-header-bg: #f1f5f9;
  --table-row-hover: #f8fafc;
  --table-stripe: #fcfcfd;
  --status-draft: #94a3b8;
  --status-pending: #f59e0b;
  --status-approved: #22c55e;
  --status-denied: #ef4444;
  --status-closed: #6b7280;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: system-ui, 'Segoe UI', sans-serif;
  font-size: 14px;
  color: #1e293b;
  background: #f1f5f9;
}

/* Table status row left bar */
.status-row-draft { border-left: 3px solid var(--status-draft); }
.status-row-pending, .status-row-po_pending { border-left: 3px solid var(--status-pending); }
.status-row-approved, .status-row-po_approved { border-left: 3px solid var(--status-approved); }
.status-row-denied { border-left: 3px solid var(--status-denied); }
.status-row-closed, .status-row-finished { border-left: 3px solid var(--status-closed); }
.status-row-cancelled { border-left: 3px solid var(--status-denied); }

/* Amount formatting */
.amount-cell {
  font-variant-numeric: tabular-nums;
  text-align: right;
}

/* Detail page */
.detail-page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}
.detail-page-header h2 {
  font-size: 20px;
  font-weight: 700;
}

/* Card sections */
.section-card {
  background: #fff;
  border-radius: 4px;
  padding: 16px;
  margin-bottom: 16px;
}
```

- [ ] **Step 2: Create LoginView.vue**

```vue
<template>
  <div class="login-screen">
    <el-card class="login-card" shadow="always">
      <h1 class="login-title">SC GR Operations</h1>
      <p class="login-subtitle">Budget & Purchase Order Management</p>

      <!-- Loading state -->
      <div v-if="state === 'loading'" class="login-state">
        <el-skeleton :rows="3" animated />
        <p style="margin-top:12px;color:#64748b">Detecting identity...</p>
      </div>

      <!-- Authorized state -->
      <div v-if="state === 'authorized'" class="login-state">
        <el-result icon="success" title="Identity Verified">
          <template #sub-title>
            <p>{{ user?.user_name }} <el-tag size="small" :type="user?.role === 'admin' ? 'danger' : ''">{{ user?.role }}</el-tag></p>
            <p style="color:#94a3b8;font-size:12px;">{{ user?.machine_id }}</p>
          </template>
          <template #extra>
            <el-button type="primary" size="large" @click="enterApp">Enter</el-button>
          </template>
        </el-result>
      </div>

      <!-- Unauthorized state -->
      <div v-if="state === 'unauthorized'" class="login-state">
        <el-result icon="error" title="Not Authorized">
          <template #sub-title>
            <p>This machine is not authorized to access the system.</p>
            <p style="color:#94a3b8;font-size:12px;margin-top:8px;">Contact your administrator.</p>
          </template>
          <template #extra>
            <el-button @click="verify">Retry</el-button>
          </template>
        </el-result>
      </div>
    </el-card>
    <p class="login-version">v2.0.0 &middot; Audi C/EV-L</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { callApi } from '@/api/bridge.js'

const router = useRouter()
const state = ref('loading')
const user = ref(null)

async function verify() {
  state.value = 'loading'
  try {
    user.value = await callApi('current_user')
    window.__currentUser = user.value
    state.value = 'authorized'
  } catch {
    state.value = 'unauthorized'
  }
}

function enterApp() {
  const redirect = router.currentRoute.value.query?.redirect || '/workbench'
  router.push(redirect)
}

onMounted(verify)
</script>

<style scoped>
.login-screen {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 100vh;
  background: #f1f5f9;
}
.login-card {
  width: 420px;
  text-align: center;
}
.login-title {
  font-size: 22px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 4px;
}
.login-subtitle {
  font-size: 13px;
  color: #94a3b8;
  margin-bottom: 24px;
}
.login-state {
  padding: 12px 0;
}
.login-version {
  margin-top: 16px;
  font-size: 12px;
  color: #94a3b8;
}
</style>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/assets/main.css frontend/src/views/LoginView.vue
git commit -m "feat: add LoginView (3 states) and CSS theme variables"
```

---

### Task 6: Composables — useUser, useVendor, useLogs

**Files:**
- Create: `frontend/src/composables/useUser.js`
- Create: `frontend/src/composables/useVendor.js`
- Create: `frontend/src/composables/useLogs.js`

- [ ] **Step 1: Create useUser.js**

```js
import { reactive, readonly } from 'vue'
import { callApi } from '@/api/bridge.js'

export function useUser() {
  const state = reactive({
    users: [],
    loading: false,
    error: null
  })

  async function fetchUsers() {
    state.loading = true
    state.error = null
    try {
      state.users = await callApi('list_users')
    } catch (e) {
      state.error = e.message
    } finally {
      state.loading = false
    }
  }

  async function createUser(data) {
    const result = await callApi('create_user', { data })
    await fetchUsers()
    return result
  }

  async function updateUser(machineId, data) {
    const result = await callApi('update_user', { machine_id: machineId, data })
    await fetchUsers()
    return result
  }

  async function disableUser(machineId) {
    await callApi('disable_user', { machine_id: machineId })
    await fetchUsers()
  }

  async function enableUser(machineId) {
    await callApi('enable_user', { machine_id: machineId })
    await fetchUsers()
  }

  return {
    state: readonly(state),
    fetchUsers,
    createUser,
    updateUser,
    disableUser,
    enableUser
  }
}
```

- [ ] **Step 2: Create useVendor.js**

```js
import { reactive, readonly } from 'vue'
import { callApi } from '@/api/bridge.js'

export function useVendor() {
  const state = reactive({
    rows: [],
    loading: false,
    error: null
  })

  async function searchVendors(text = null) {
    state.loading = true
    state.error = null
    try {
      state.rows = await callApi('search_vendors', { text })
    } catch (e) {
      state.error = e.message
      state.rows = []
    } finally {
      state.loading = false
    }
  }

  async function createVendor(data) {
    const result = await callApi('create_vendor', { data })
    await searchVendors()
    return result
  }

  async function updateVendor(vendorId, data) {
    const result = await callApi('update_vendor', { vendor_id: vendorId, data })
    await searchVendors()
    return result
  }

  async function disableVendor(vendorId) {
    await callApi('disable_vendor', { vendor_id: vendorId })
    await searchVendors()
  }

  return {
    state: readonly(state),
    searchVendors,
    createVendor,
    updateVendor,
    disableVendor
  }
}
```

- [ ] **Step 3: Create useLogs.js**

```js
import { reactive, readonly } from 'vue'
import { callApi } from '@/api/bridge.js'

export function useLogs(pageSize = 50) {
  const state = reactive({
    rows: [],
    total: 0,
    loading: false,
    error: null,
    filters: {},
    sort: 'created_at',
    direction: 'desc',
    pageSize: pageSize,
    currentPage: 1
  })

  async function searchLogs(text = null, filters = null) {
    state.loading = true
    state.error = null
    try {
      const payload = {
        text,
        filters,
        sort: state.sort,
        direction: state.direction,
        limit: state.pageSize,
        offset: (state.currentPage - 1) * state.pageSize
      }
      const result = await callApi('search_audit_logs', payload)
      state.rows = result.rows || result
      state.total = result.total || state.rows.length
    } catch (e) {
      state.error = e.message
      state.rows = []
    } finally {
      state.loading = false
    }
  }

  function setFilters(filters) {
    Object.assign(state.filters, filters)
    state.currentPage = 1
  }

  function resetFilters() {
    state.filters = {}
    state.currentPage = 1
  }

  function onSortChange({ prop, order }) {
    state.sort = prop || 'created_at'
    state.direction = order === 'ascending' ? 'asc' : 'desc'
  }

  function onPageChange(page) {
    state.currentPage = page
  }

  function onPageSizeChange(size) {
    state.pageSize = size
    state.currentPage = 1
  }

  return {
    state: readonly(state),
    searchLogs,
    setFilters,
    resetFilters,
    onSortChange,
    onPageChange,
    onPageSizeChange
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/composables/useUser.js frontend/src/composables/useVendor.js frontend/src/composables/useLogs.js
git commit -m "feat: add composables — useUser, useVendor, useLogs"
```

---

### Task 7: Composables — useSc, usePo, useGr

**Files:**
- Create: `frontend/src/composables/useSc.js`
- Create: `frontend/src/composables/usePo.js`
- Create: `frontend/src/composables/useGr.js`

- [ ] **Step 1: Create useSc.js**

```js
import { reactive, readonly } from 'vue'
import { callApi } from '@/api/bridge.js'

export function useSc(pageSize = 20) {
  const state = reactive({
    rows: [],
    total: 0,
    loading: false,
    error: null,
    filters: {},
    sort: 'created_at',
    direction: 'desc',
    pageSize,
    currentPage: 1,
    detail: null,
    detailLoading: false,
    detailError: null
  })

  async function searchScs(text = null, filters = null) {
    state.loading = true
    state.error = null
    try {
      const payload = {
        text,
        filters,
        sort: state.sort,
        direction: state.direction,
        limit: state.pageSize,
        offset: (state.currentPage - 1) * state.pageSize
      }
      const result = await callApi('search_scs', payload)
      state.rows = result.rows || result
      state.total = result.total || state.rows.length
    } catch (e) {
      state.error = e.message
      state.rows = []
    } finally {
      state.loading = false
    }
  }

  async function fetchDetail(scId) {
    state.detailLoading = true
    state.detailError = null
    try {
      state.detail = await callApi('get_sc_detail', { sc_id: scId })
    } catch (e) {
      state.detailError = e.message
      state.detail = null
    } finally {
      state.detailLoading = false
    }
  }

  async function createDraft(data) {
    return await callApi('create_sc_draft', { data })
  }

  async function submitSc(data) {
    return await callApi('submit_sc', { data })
  }

  async function updateSc(data) {
    return await callApi('update_sc', { data })
  }

  async function approveSc(scId) {
    await callApi('approve_sc', { sc_id: scId })
  }

  async function denySc(scId) {
    await callApi('deny_sc', { sc_id: scId })
  }

  async function closeSc(scId) {
    await callApi('close_sc', { sc_id: scId })
  }

  function setFilters(filters) {
    Object.assign(state.filters, filters)
    state.currentPage = 1
  }

  function resetFilters() {
    state.filters = {}
    state.currentPage = 1
  }

  function onSortChange({ prop, order }) {
    state.sort = prop || 'created_at'
    state.direction = order === 'ascending' ? 'asc' : 'desc'
  }

  function onPageChange(page) { state.currentPage = page }
  function onPageSizeChange(size) { state.pageSize = size; state.currentPage = 1 }

  return {
    state: readonly(state),
    searchScs, fetchDetail,
    createDraft, submitSc, updateSc,
    approveSc, denySc, closeSc,
    setFilters, resetFilters,
    onSortChange, onPageChange, onPageSizeChange
  }
}
```

- [ ] **Step 2: Create usePo.js**

```js
import { reactive, readonly } from 'vue'
import { callApi } from '@/api/bridge.js'

export function usePo(pageSize = 20) {
  const state = reactive({
    rows: [],
    total: 0,
    loading: false,
    error: null,
    filters: {},
    sort: 'created_at',
    direction: 'desc',
    pageSize,
    currentPage: 1
  })

  async function searchPos(text = null, filters = null) {
    state.loading = true
    state.error = null
    try {
      const payload = {
        text,
        filters,
        sort: state.sort,
        direction: state.direction,
        limit: state.pageSize,
        offset: (state.currentPage - 1) * state.pageSize
      }
      const result = await callApi('search_pos', payload)
      state.rows = result.rows || result
      state.total = result.total || state.rows.length
    } catch (e) {
      state.error = e.message
      state.rows = []
    } finally {
      state.loading = false
    }
  }

  async function createPo(data) {
    return await callApi('create_po', { data })
  }

  async function updatePo(data) {
    return await callApi('update_po', { data })
  }

  async function approvePo(poId) {
    await callApi('approve_po', { po_id: poId })
  }

  async function finishPo(poId) {
    await callApi('finish_po', { po_id: poId })
  }

  function setFilters(filters) { Object.assign(state.filters, filters); state.currentPage = 1 }
  function resetFilters() { state.filters = {}; state.currentPage = 1 }
  function onSortChange({ prop, order }) { state.sort = prop || 'created_at'; state.direction = order === 'ascending' ? 'asc' : 'desc' }
  function onPageChange(page) { state.currentPage = page }
  function onPageSizeChange(size) { state.pageSize = size; state.currentPage = 1 }

  return {
    state: readonly(state),
    searchPos, createPo, updatePo, approvePo, finishPo,
    setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange
  }
}
```

- [ ] **Step 3: Create useGr.js**

```js
import { reactive, readonly } from 'vue'
import { callApi } from '@/api/bridge.js'

export function useGr(pageSize = 20) {
  const state = reactive({
    rows: [],
    total: 0,
    loading: false,
    error: null,
    filters: {},
    sort: 'created_at',
    direction: 'desc',
    pageSize,
    currentPage: 1
  })

  async function searchGrs(text = null, filters = null) {
    state.loading = true
    state.error = null
    try {
      const payload = {
        text,
        filters,
        sort: state.sort,
        direction: state.direction,
        limit: state.pageSize,
        offset: (state.currentPage - 1) * state.pageSize
      }
      const result = await callApi('search_grs', payload)
      state.rows = result.rows || result
      state.total = result.total || state.rows.length
    } catch (e) {
      state.error = e.message
      state.rows = []
    } finally {
      state.loading = false
    }
  }

  async function createGr(data) { return await callApi('create_gr', { data }) }
  async function updateGr(data) { return await callApi('update_gr', { data }) }
  async function approveGr(grId) { await callApi('approve_gr', { gr_id: grId }) }
  async function cancelGr(grId) { await callApi('cancel_gr', { gr_id: grId }) }

  function setFilters(filters) { Object.assign(state.filters, filters); state.currentPage = 1 }
  function resetFilters() { state.filters = {}; state.currentPage = 1 }
  function onSortChange({ prop, order }) { state.sort = prop || 'created_at'; state.direction = order === 'ascending' ? 'asc' : 'desc' }
  function onPageChange(page) { state.currentPage = page }
  function onPageSizeChange(size) { state.pageSize = size; state.currentPage = 1 }

  return {
    state: readonly(state),
    searchGrs, createGr, updateGr, approveGr, cancelGr,
    setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/composables/useSc.js frontend/src/composables/usePo.js frontend/src/composables/useGr.js
git commit -m "feat: add composables — useSc, usePo, useGr"
```

---

### Task 8: SC components — ScTable, ScDetailCard, ScFormDialog

**Files:**
- Create: `frontend/src/components/sc/ScTable.vue`
- Create: `frontend/src/components/sc/ScDetailCard.vue`
- Create: `frontend/src/components/sc/ScFormDialog.vue`

- [ ] **Step 1: Create ScTable.vue**

```vue
<template>
  <el-table
    :data="rows"
    v-loading="loading"
    stripe
    border
    @sort-change="$emit('sort-change', $event)"
    @row-click="$emit('row-click', $event)"
    :row-class-name="rowClass"
    style="cursor:pointer"
  >
    <el-table-column label="Status" width="100">
      <template #default="{ row }">
        <StatusBadge :status="row.status" />
      </template>
    </el-table-column>
    <el-table-column prop="sc_no" label="SC No" sortable="custom" width="130" />
    <el-table-column prop="requester_name" label="Requester" sortable="custom" width="130" />
    <el-table-column prop="request_type" label="Type" sortable="custom" width="110" />
    <el-table-column prop="cost_center" label="Cost Center" sortable="custom" width="110" />
    <el-table-column prop="sc_amount" label="SC Amount" sortable="custom" width="130">
      <template #default="{ row }">
        <AmountDisplay :value="row.sc_amount" />
      </template>
    </el-table-column>
    <el-table-column prop="created_at" label="Created" sortable="custom" width="120">
      <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
    </el-table-column>
    <el-table-column prop="description" label="Description" min-width="150" show-overflow-tooltip />
    <el-table-column label="Actions" width="70" fixed="right">
      <template #default>
        <el-button type="primary" link size="small">Detail</el-button>
      </template>
    </el-table-column>
    <template #empty>
      <el-empty :description="emptyText" />
    </template>
  </el-table>
</template>

<script setup>
import { computed } from 'vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  emptyText: { type: String, default: 'No SC records match the search and filters.' }
})

defineEmits(['sort-change', 'row-click'])

function rowClass({ row }) {
  return `status-row-${row.status || ''}`
}

function formatDate(val) {
  if (!val) return '-'
  return val.slice(0, 10)
}
</script>
```

- [ ] **Step 2: Create ScDetailCard.vue**

```vue
<template>
  <el-descriptions :column="2" border size="small" class="sc-descriptions">
    <el-descriptions-item label="SC ID">{{ sc.sc_id }}</el-descriptions-item>
    <el-descriptions-item label="SC No">{{ sc.sc_no || '-' }}</el-descriptions-item>
    <el-descriptions-item label="Requester">{{ sc.requester_id }}</el-descriptions-item>
    <el-descriptions-item label="Request Type">{{ sc.request_type }}</el-descriptions-item>
    <el-descriptions-item label="Cost Center">{{ sc.cost_center || '-' }}</el-descriptions-item>
    <el-descriptions-item label="SC Amount"><AmountDisplay :value="sc.sc_amount" /></el-descriptions-item>
    <el-descriptions-item label="Service Period Start">{{ formatDate(sc.service_period_start) }}</el-descriptions-item>
    <el-descriptions-item label="Service Period End">{{ formatDate(sc.service_period_end) }}</el-descriptions-item>
    <el-descriptions-item label="Description" :span="2">{{ sc.description || '-' }}</el-descriptions-item>
    <el-descriptions-item label="Created At">{{ formatDate(sc.created_at) }}</el-descriptions-item>
    <el-descriptions-item label="Updated At">{{ formatDate(sc.updated_at) }}</el-descriptions-item>
  </el-descriptions>
</template>

<script setup>
import AmountDisplay from '@/components/common/AmountDisplay.vue'

defineProps({
  sc: { type: Object, required: true }
})

function formatDate(val) {
  if (!val) return '-'
  return val.slice(0, 10)
}
</script>
```

- [ ] **Step 3: Create ScFormDialog.vue**

```vue
<template>
  <el-dialog
    :model-value="visible"
    :title="mode === 'edit' ? 'Edit SC' : 'New SC'"
    width="640px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="SC ID" prop="sc_id">
            <el-input v-model="form.sc_id" :disabled="mode === 'edit'" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="SC No">
            <el-input v-model="form.sc_no" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="Requester" prop="requester_id">
            <el-select v-model="form.requester_id" filterable>
              <el-option v-for="u in users" :key="u.user_id" :label="`${u.user_name} — ${u.machine_id}`" :value="u.user_id" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="Request Type">
            <el-select v-model="form.request_type">
              <el-option v-for="t in requestTypes" :key="t" :label="t" :value="t" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="Cost Center">
            <el-input v-model="form.cost_center" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="SC Amount">
            <el-input-number v-model="form.sc_amount" :precision="2" :min="0" controls-position="right" style="width:100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="Service Period Start">
            <el-date-picker v-model="form.service_period_start" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="Service Period End">
            <el-date-picker v-model="form.service_period_end" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="Description">
        <el-input v-model="form.description" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)" :disabled="submitting">Cancel</el-button>
      <el-button v-if="mode === 'create'" @click="saveDraft" :disabled="submitting">Save Draft</el-button>
      <el-button type="primary" @click="saveSubmit" :loading="submitting">
        {{ mode === 'edit' ? 'Save' : 'Submit' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  visible: { type: Boolean, default: false },
  mode: { type: String, default: 'create' },
  record: { type: Object, default: null },
  users: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:visible', 'save-draft', 'save-submit'])

const requestTypes = ['material', 'service', 'fixed_asset', 'FC']
const formRef = ref()
const submitting = ref(false)

const emptyForm = () => ({
  sc_id: '',
  sc_no: '',
  requester_id: '',
  request_type: '',
  cost_center: '',
  sc_amount: null,
  service_period_start: null,
  service_period_end: null,
  description: ''
})

const form = reactive(emptyForm())

const rules = {
  sc_id: [{ required: true, message: 'SC ID is required', trigger: 'blur' }],
  requester_id: [{ required: true, message: 'Requester is required', trigger: 'change' }]
}

watch(() => props.visible, (val) => {
  if (val && props.mode === 'edit' && props.record) {
    Object.assign(form, props.record)
  } else if (val) {
    Object.assign(form, emptyForm())
  }
})

async function saveDraft() {
  submitting.value = true
  try {
    emit('save-draft', { ...form })
    emit('update:visible', false)
    ElMessage.success('Draft saved')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}

async function saveSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch { return }
  submitting.value = true
  try {
    emit('save-submit', { ...form })
    emit('update:visible', false)
    ElMessage.success('Saved')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}
</script>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/sc/ScTable.vue frontend/src/components/sc/ScDetailCard.vue frontend/src/components/sc/ScFormDialog.vue
git commit -m "feat: add SC components — ScTable, ScDetailCard, ScFormDialog"
```

---

### Task 9: PO components — PoTable, PoFormDialog, GrTable, GrFormDialog

**Files:**
- Create: `frontend/src/components/po/PoTable.vue`
- Create: `frontend/src/components/po/PoFormDialog.vue`
- Create: `frontend/src/components/po/GrTable.vue`
- Create: `frontend/src/components/po/GrFormDialog.vue`

- [ ] **Step 1: Create PoTable.vue**

```vue
<template>
  <el-table
    :data="rows"
    v-loading="loading"
    stripe
    border
    @row-click="$emit('row-click', $event)"
    :row-class-name="rowClass"
    style="cursor:pointer"
  >
    <el-table-column label="Status" width="100">
      <template #default="{ row }"><StatusBadge :status="row.status" /></template>
    </el-table-column>
    <el-table-column prop="po_no" label="PO No" width="130">
      <template #default="{ row }">{{ row.po_no || row.po_id }}</template>
    </el-table-column>
    <el-table-column prop="vendor_name" label="Vendor" width="160" show-overflow-tooltip />
    <el-table-column prop="po_amount" label="PO Amount" width="120">
      <template #default="{ row }"><AmountDisplay :value="row.po_amount" /></template>
    </el-table-column>
    <el-table-column prop="open_po_amount" label="Open/Con" width="120">
      <template #default="{ row }"><AmountDisplay :value="row.open_po_amount" /></template>
    </el-table-column>
    <el-table-column prop="contract_from" label="Contract From" width="120">
      <template #default="{ row }">{{ formatDate(row.contract_from) }}</template>
    </el-table-column>
    <el-table-column prop="contract_to" label="Contract To" width="120">
      <template #default="{ row }">{{ formatDate(row.contract_to) }}</template>
    </el-table-column>
    <el-table-column label="Actions" width="140" fixed="right">
      <template #default="{ row }">
        <el-button type="primary" link size="small" @click.stop="$emit('edit', row)">Edit</el-button>
        <el-button v-if="row.status === 'po_pending'" type="success" link size="small" @click.stop="$emit('approve', row)">Approve</el-button>
        <el-button v-if="row.status === 'po_approved'" type="info" link size="small" @click.stop="$emit('finish', row)">Finish</el-button>
      </template>
    </el-table-column>
    <template #empty><el-empty description="No PO records." /></template>
  </el-table>
</template>

<script setup>
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'

defineProps({
  rows: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false }
})

defineEmits(['row-click', 'edit', 'approve', 'finish'])

function rowClass({ row }) { return `status-row-${row.status || ''}` }
function formatDate(val) { return val ? val.slice(0, 10) : '-' }
</script>
```

- [ ] **Step 2: Create PoFormDialog.vue**

```vue
<template>
  <el-dialog
    :model-value="visible"
    :title="mode === 'edit' ? 'Edit PO' : 'Add PO'"
    width="520px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="PO ID" prop="po_id">
            <el-input v-model="form.po_id" :disabled="mode === 'edit'" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="PO No">
            <el-input v-model="form.po_no" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="Vendor" prop="vendor_id">
        <el-select v-model="form.vendor_id" filterable>
          <el-option v-for="v in vendors" :key="v.vendor_id" :label="`${v.vendor_name} — KSRM: ${v.ksrm_vendor_code || '-'}`" :value="v.vendor_id" />
        </el-select>
      </el-form-item>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="PO Amount">
            <el-input-number v-model="form.po_amount" :precision="2" :min="0" controls-position="right" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="Contract No">
            <el-input v-model="form.contract_no" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="Contract From">
            <el-date-picker v-model="form.contract_from" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="Contract To">
            <el-date-picker v-model="form.contract_to" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="Payment Frequency">
        <el-input v-model="form.payment_frequency" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)" :disabled="submitting">Cancel</el-button>
      <el-button type="primary" @click="handleSave" :loading="submitting">Save</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  visible: Boolean,
  mode: { type: String, default: 'create' },
  record: Object,
  vendors: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:visible', 'save'])

const formRef = ref()
const submitting = ref(false)

const emptyForm = () => ({
  po_id: '', po_no: '', vendor_id: '', po_amount: null,
  contract_from: null, contract_to: null, contract_no: '', payment_frequency: ''
})

const form = reactive(emptyForm())

const rules = {
  po_id: [{ required: true, message: 'PO ID is required', trigger: 'blur' }],
  vendor_id: [{ required: true, message: 'Vendor is required', trigger: 'change' }]
}

watch(() => props.visible, (val) => {
  if (val && props.mode === 'edit' && props.record) {
    Object.assign(form, props.record)
  } else if (val) {
    Object.assign(form, emptyForm())
  }
})

async function handleSave() {
  if (!formRef.value) return
  try { await formRef.value.validate() } catch { return }
  submitting.value = true
  try {
    emit('save', { ...form })
    emit('update:visible', false)
    ElMessage.success('Saved')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}
</script>
```

- [ ] **Step 3: Create GrTable.vue**

```vue
<template>
  <el-table :data="rows" stripe border style="width:100%">
    <el-table-column label="Status" width="100">
      <template #default="{ row }"><StatusBadge :status="row.status" /></template>
    </el-table-column>
    <el-table-column prop="gr_id" label="GR ID" width="120" />
    <el-table-column prop="requester_id" label="Requester" width="120" />
    <el-table-column prop="estimated_amount" label="Estimated" width="120">
      <template #default="{ row }"><AmountDisplay :value="row.estimated_amount" /></template>
    </el-table-column>
    <el-table-column prop="con_value" label="Con Value" width="120">
      <template #default="{ row }"><AmountDisplay :value="row.con_value" /></template>
    </el-table-column>
    <el-table-column prop="remark" label="Remark" min-width="140" show-overflow-tooltip />
    <el-table-column prop="created_at" label="Created" width="110">
      <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
    </el-table-column>
    <el-table-column label="Actions" width="180" fixed="right">
      <template #default="{ row }">
        <el-button type="primary" link size="small" @click="$emit('edit', row)">Edit</el-button>
        <el-button v-if="row.status === 'pending'" type="success" link size="small" @click="$emit('approve', row)">Approve</el-button>
        <el-popconfirm v-if="row.status === 'pending'" title="Cancel this GR?" @confirm="$emit('cancel', row)">
          <template #reference>
            <el-button type="danger" link size="small">Cancel</el-button>
          </template>
        </el-popconfirm>
      </template>
    </el-table-column>
    <template #empty><el-empty description="No GRs for this PO." /></template>
  </el-table>
</template>

<script setup>
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'

defineProps({ rows: { type: Array, default: () => [] } })
defineEmits(['edit', 'approve', 'cancel'])

function formatDate(val) { return val ? val.slice(0, 10) : '-' }
</script>
```

- [ ] **Step 4: Create GrFormDialog.vue**

```vue
<template>
  <el-dialog
    :model-value="visible"
    :title="mode === 'edit' ? 'Edit GR' : 'Add GR'"
    width="520px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="GR ID" prop="gr_id">
            <el-input v-model="form.gr_id" :disabled="mode === 'edit'" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="Requester ID">
            <el-input v-model="form.requester_id" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="Estimated Amount">
            <el-input-number v-model="form.estimated_amount" :precision="2" :min="0" controls-position="right" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="Con Value">
            <el-input-number v-model="form.con_value" :precision="2" :min="0" controls-position="right" style="width:100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="Remark">
        <el-input v-model="form.remark" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)" :disabled="submitting">Cancel</el-button>
      <el-button type="primary" @click="handleSave" :loading="submitting">Save</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  visible: Boolean,
  mode: { type: String, default: 'create' },
  record: Object
})

const emit = defineEmits(['update:visible', 'save'])

const formRef = ref()
const submitting = ref(false)

const emptyForm = () => ({
  gr_id: '', requester_id: '', estimated_amount: null, con_value: null, remark: ''
})

const form = reactive(emptyForm())

const rules = {
  gr_id: [{ required: true, message: 'GR ID is required', trigger: 'blur' }]
}

watch(() => props.visible, (val) => {
  if (val && props.mode === 'edit' && props.record) {
    Object.assign(form, props.record)
  } else if (val) {
    Object.assign(form, emptyForm())
  }
})

async function handleSave() {
  if (!formRef.value) return
  try { await formRef.value.validate() } catch { return }
  submitting.value = true
  try {
    emit('save', { ...form })
    emit('update:visible', false)
    ElMessage.success('Saved')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}
</script>
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/po/PoTable.vue frontend/src/components/po/PoFormDialog.vue frontend/src/components/po/GrTable.vue frontend/src/components/po/GrFormDialog.vue
git commit -m "feat: add PO/GR components — PoTable, PoFormDialog, GrTable, GrFormDialog"
```

---

### Task 10: Vendor + User dialog components

**Files:**
- Create: `frontend/src/components/vendor/VendorFormDialog.vue`
- Create: `frontend/src/components/system/UserFormDialog.vue`

- [ ] **Step 1: Create VendorFormDialog.vue**

```vue
<template>
  <el-dialog
    :model-value="visible"
    :title="mode === 'edit' ? 'Edit Vendor' : 'Add Vendor'"
    width="520px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="Vendor ID" prop="vendor_id">
            <el-input v-model="form.vendor_id" :disabled="mode === 'edit'" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="Vendor Name" prop="vendor_name">
            <el-input v-model="form.vendor_name" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="Service Scope" prop="service_scope">
        <el-select v-model="form.service_scope" filterable>
          <el-option v-for="s in serviceScopes" :key="s" :label="s" :value="s" />
        </el-select>
      </el-form-item>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="KSRM Code">
            <el-input v-model="form.ksrm_vendor_code" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="Contact Person">
            <el-input v-model="form.contact_person" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="Phone">
            <el-input v-model="form.phone" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="Email">
            <el-input v-model="form.email" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="Description">
        <el-input v-model="form.description" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="Inquiry History">
        <el-input v-model="form.inquiry_history" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)" :disabled="submitting">Cancel</el-button>
      <el-button type="primary" @click="handleSave" :loading="submitting">Save</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  visible: Boolean,
  mode: { type: String, default: 'create' },
  record: Object
})

const emit = defineEmits(['update:visible', 'save'])

const formRef = ref()
const submitting = ref(false)

const serviceScopes = [
  'Transportation', 'engineering Service', 'Equipment', 'Parts', 'Driver',
  'Test car rental', 'General Service', 'Dealers', 'Import&Export&cusoms clearance',
  'Insurance', 'Harness', 'Maintenance', 'Security', 'Testing support', 'Others'
]

const emptyForm = () => ({
  vendor_id: '', vendor_name: '', service_scope: '', ksrm_vendor_code: '',
  contact_person: '', phone: '', email: '', description: '', inquiry_history: ''
})

const form = reactive(emptyForm())

const rules = {
  vendor_id: [{ required: true, message: 'Vendor ID is required', trigger: 'blur' }],
  vendor_name: [{ required: true, message: 'Vendor Name is required', trigger: 'blur' }],
  service_scope: [{ required: true, message: 'Service Scope is required', trigger: 'change' }]
}

watch(() => props.visible, (val) => {
  if (val && props.mode === 'edit' && props.record) {
    Object.assign(form, props.record)
  } else if (val) {
    Object.assign(form, emptyForm())
  }
})

async function handleSave() {
  if (!formRef.value) return
  try { await formRef.value.validate() } catch { return }
  submitting.value = true
  try {
    emit('save', { ...form })
    emit('update:visible', false)
    ElMessage.success('Saved')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}
</script>
```

- [ ] **Step 2: Create UserFormDialog.vue**

```vue
<template>
  <el-dialog
    :model-value="visible"
    :title="mode === 'edit' ? 'Edit User' : 'Add User'"
    width="480px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item label="Machine ID" prop="machine_id">
        <el-input v-model="form.machine_id" :disabled="mode === 'edit'" maxlength="7" />
      </el-form-item>
      <el-form-item label="Name" prop="user_name">
        <el-input v-model="form.user_name" />
      </el-form-item>
      <el-form-item label="Email">
        <el-input v-model="form.email" />
      </el-form-item>
      <el-form-item label="Role" prop="role">
        <el-select v-model="form.role">
          <el-option label="Requester" value="requester" />
          <el-option label="Admin" value="admin" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)" :disabled="submitting">Cancel</el-button>
      <el-button type="primary" @click="handleSave" :loading="submitting">Save</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  visible: Boolean,
  mode: { type: String, default: 'create' },
  record: Object
})

const emit = defineEmits(['update:visible', 'save'])

const formRef = ref()
const submitting = ref(false)

const emptyForm = () => ({
  machine_id: '', user_name: '', email: '', role: 'requester'
})

const form = reactive(emptyForm())

const rules = {
  machine_id: [{ required: true, message: 'Machine ID is required', trigger: 'blur' }],
  user_name: [{ required: true, message: 'Name is required', trigger: 'blur' }],
  role: [{ required: true, message: 'Role is required', trigger: 'change' }]
}

watch(() => props.visible, (val) => {
  if (val && props.mode === 'edit' && props.record) {
    Object.assign(form, props.record)
  } else if (val) {
    Object.assign(form, emptyForm())
  }
})

async function handleSave() {
  if (!formRef.value) return
  try { await formRef.value.validate() } catch { return }
  submitting.value = true
  try {
    emit('save', { ...form })
    emit('update:visible', false)
    ElMessage.success('Saved')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}
</script>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/vendor/VendorFormDialog.vue frontend/src/components/system/UserFormDialog.vue
git commit -m "feat: add VendorFormDialog and UserFormDialog components"
```

---

### Task 11: List views — ScListView, PoListView, GrListView

**Files:**
- Create: `frontend/src/views/ScListView.vue`
- Create: `frontend/src/views/PoListView.vue`
- Create: `frontend/src/views/GrListView.vue`

- [ ] **Step 1: Create ScListView.vue**

```vue
<template>
  <div>
    <FilterBar @reset="handleReset">
      <template #filters>
        <el-select v-model="filters.status" placeholder="Status" clearable @change="onFilterChange">
          <el-option v-for="s in scStatuses" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-select v-model="filters.request_type" placeholder="Request Type" clearable @change="onFilterChange">
          <el-option v-for="t in requestTypes" :key="t" :label="t" :value="t" />
        </el-select>
        <el-input v-model="filters.cost_center" placeholder="Cost Center" clearable @change="onFilterChange" style="width:150px" />
      </template>
      <template #actions>
        <el-button type="primary" @click="scDialogVisible = true; scDialogMode = 'create'">
          <el-icon><Plus /></el-icon> New SC
        </el-button>
      </template>
    </FilterBar>

    <ScTable
      :rows="state.rows"
      :loading="state.loading"
      :empty-text="state.error || 'No SC records match the search and filters.'"
      @sort-change="handleSortChange"
      @row-click="row => $router.push(`/sc/${row.sc_id}`)"
    />

    <el-pagination
      v-if="state.total > state.pageSize"
      :current-page="state.currentPage"
      :page-size="state.pageSize"
      :total="state.total"
      layout="total, sizes, prev, pager, next, jumper"
      @current-change="handlePageChange"
      @size-change="handleSizeChange"
      style="margin-top:12px;justify-content:flex-end"
    />

    <ScFormDialog
      v-model:visible="scDialogVisible"
      :mode="scDialogMode"
      :record="scDialogRecord"
      :users="activeUsers"
      @save-draft="handleSaveDraft"
      @save-submit="handleSaveSubmit"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { useSc } from '@/composables/useSc.js'
import { callApi } from '@/api/bridge.js'
import FilterBar from '@/components/common/FilterBar.vue'
import ScTable from '@/components/sc/ScTable.vue'
import ScFormDialog from '@/components/sc/ScFormDialog.vue'
import { ElMessage } from 'element-plus'

const { state, searchScs, createDraft, submitSc, setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange } = useSc()

const scStatuses = [
  { label: 'Pending', value: 'pending' }, { label: 'Approved', value: 'approved' },
  { label: 'Denied', value: 'denied' }, { label: 'Closed', value: 'closed' }
]
const requestTypes = ['material', 'service', 'fixed_asset', 'FC']
const activeUsers = ref([])

const filters = reactive({ status: '', request_type: '', cost_center: '' })

const scDialogVisible = ref(false)
const scDialogMode = ref('create')
const scDialogRecord = ref(null)

function onFilterChange() {
  const f = {}
  if (filters.status) f.status = filters.status
  if (filters.request_type) f.request_type = filters.request_type
  if (filters.cost_center) f.cost_center = filters.cost_center
  setFilters(f)
  searchScs(null, f)
}

function handleReset() {
  Object.assign(filters, { status: '', request_type: '', cost_center: '' })
  resetFilters()
  searchScs()
}

function handleSortChange({ prop, order }) {
  onSortChange({ prop, order })
  searchScs()
}

function handlePageChange(page) { onPageChange(page); searchScs() }
function handleSizeChange(size) { onPageSizeChange(size); searchScs() }

async function handleSaveDraft(data) {
  try {
    await createDraft(data)
    await searchScs()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}

async function handleSaveSubmit(data) {
  try {
    await submitSc(data)
    await searchScs()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}

onMounted(async () => {
  try {
    activeUsers.value = await callApi('list_users')
  } catch { /* ignore */ }
  await searchScs()
})
</script>
```

- [ ] **Step 2: Create PoListView.vue**

```vue
<template>
  <div>
    <FilterBar @reset="handleReset">
      <template #filters>
        <el-select v-model="filters.status" placeholder="Status" clearable @change="onFilterChange">
          <el-option v-for="s in poStatuses" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-date-picker v-model="filters.contract_to" type="date" placeholder="Contract To" value-format="YYYY-MM-DD" @change="onFilterChange" />
        <el-select v-model="filters.open_po" placeholder="OPEN PO" clearable @change="onFilterChange">
          <el-option label="Open" value="open" />
          <el-option label="Closed" value="closed" />
        </el-select>
      </template>
    </FilterBar>

    <PoTable
      :rows="filteredRows"
      :loading="state.loading"
      @row-click="$router.push(`/sc/${row.sc_id}/po/${row.po_id}`)"
      @edit="row => { poDialogRecord = row; poDialogMode = 'edit'; poDialogVisible = true }"
      @approve="row => handleApprovePo(row)"
      @finish="row => handleFinishPo(row)"
    />

    <el-pagination
      v-if="state.total > state.pageSize"
      :current-page="state.currentPage"
      :page-size="state.pageSize"
      :total="state.total"
      layout="total, sizes, prev, pager, next, jumper"
      @current-change="handlePageChange"
      @size-change="handleSizeChange"
      style="margin-top:12px;justify-content:flex-end"
    />

    <PoFormDialog
      v-model:visible="poDialogVisible"
      :mode="poDialogMode"
      :record="poDialogRecord"
      :vendors="vendors"
      @save="handlePoSave"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { usePo } from '@/composables/usePo.js'
import { useVendor } from '@/composables/useVendor.js'
import FilterBar from '@/components/common/FilterBar.vue'
import PoTable from '@/components/po/PoTable.vue'
import PoFormDialog from '@/components/po/PoFormDialog.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const { state, searchPos, createPo, updatePo, approvePo, finishPo, setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange } = usePo()
const { state: vendorState, searchVendors } = useVendor()

const vendors = computed(() => vendorState.rows)

const poStatuses = [
  { label: 'Pending', value: 'po_pending' }, { label: 'Approved', value: 'po_approved' },
  { label: 'Finished', value: 'finished' }
]

const filters = reactive({ status: '', contract_to: '', open_po: '' })
const poDialogVisible = ref(false)
const poDialogMode = ref('create')
const poDialogRecord = ref(null)

const filteredRows = computed(() => {
  let rows = state.rows
  if (filters.contract_to) {
    rows = rows.filter(r => r.contract_to?.slice(0, 10) === filters.contract_to)
  }
  if (filters.open_po === 'open') {
    rows = rows.filter(r => (r.open_po_amount || r.po_amount || 0) > 0)
  } else if (filters.open_po === 'closed') {
    rows = rows.filter(r => (r.open_po_amount || 0) <= 0)
  }
  return rows
})

function onFilterChange() {
  const f = {}
  if (filters.status) f.status = filters.status
  setFilters(f)
  searchPos(null, f)
}

function handleReset() {
  Object.assign(filters, { status: '', contract_to: '', open_po: '' })
  resetFilters()
  searchPos()
}

async function handleApprovePo(row) {
  try {
    await ElMessageBox.confirm('Approve this PO?', 'Confirm', { type: 'warning' })
    await approvePo(row.po_id)
    ElMessage.success('PO approved')
    await searchPos()
  } catch { /* cancelled */ }
}

async function handleFinishPo(row) {
  try {
    await ElMessageBox.confirm('Finish this PO?', 'Confirm', { type: 'warning' })
    await finishPo(row.po_id)
    ElMessage.success('PO finished')
    await searchPos()
  } catch { /* cancelled */ }
}

async function handlePoSave(data) {
  try {
    if (poDialogMode.value === 'create') {
      await createPo(data)
    } else {
      await updatePo(data)
    }
    await searchPos()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}

function handlePageChange(page) { onPageChange(page); searchPos() }
function handleSizeChange(size) { onPageSizeChange(size); searchPos() }

onMounted(async () => {
  await Promise.all([searchPos(), searchVendors()])
})
</script>
```

- [ ] **Step 3: Create GrListView.vue**

```vue
<template>
  <div>
    <FilterBar @reset="handleReset">
      <template #filters>
        <el-select v-model="filters.status" placeholder="Status" clearable @change="onFilterChange">
          <el-option v-for="s in grStatuses" :key="s.label" :label="s.label" :value="s.value" />
        </el-select>
        <el-input-number v-model="filters.amount_min" placeholder="Amount min" :min="0" controls-position="right" @change="onFilterChange" style="width:160px" />
        <el-input-number v-model="filters.amount_max" placeholder="Amount max" :min="0" controls-position="right" @change="onFilterChange" style="width:160px" />
      </template>
    </FilterBar>

    <el-table :data="filteredRows" v-loading="state.loading" stripe border>
      <el-table-column label="Status" width="100">
        <template #default="{ row }"><StatusBadge :status="row.status" /></template>
      </el-table-column>
      <el-table-column prop="gr_id" label="GR ID" width="120" />
      <el-table-column prop="po_no" label="PO No" width="130" />
      <el-table-column prop="sc_no" label="SC No" width="130" />
      <el-table-column prop="vendor_name" label="Vendor" min-width="150" show-overflow-tooltip />
      <el-table-column prop="estimated_amount" label="Estimated" width="120">
        <template #default="{ row }"><AmountDisplay :value="row.estimated_amount" /></template>
      </el-table-column>
      <el-table-column prop="con_value" label="Con Value" width="120">
        <template #default="{ row }"><AmountDisplay :value="row.con_value" /></template>
      </el-table-column>
      <template #empty><el-empty description="No GR records found." /></template>
    </el-table>

    <el-pagination
      v-if="state.total > state.pageSize"
      :current-page="state.currentPage"
      :page-size="state.pageSize"
      :total="state.total"
      layout="total, sizes, prev, pager, next, jumper"
      @current-change="handlePageChange"
      @size-change="handleSizeChange"
      style="margin-top:12px;justify-content:flex-end"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useGr } from '@/composables/useGr.js'
import FilterBar from '@/components/common/FilterBar.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'

const { state, searchGrs, setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange } = useGr()

const grStatuses = [
  { label: 'Pending', value: 'pending' }, { label: 'Approved', value: 'approved' }, { label: 'Cancelled', value: 'cancelled' }
]

const filters = reactive({ status: '', amount_min: null, amount_max: null })

const filteredRows = computed(() => {
  let rows = state.rows
  if (filters.amount_min != null) {
    rows = rows.filter(r => (Number(r.estimated_amount) || 0) >= filters.amount_min)
  }
  if (filters.amount_max != null) {
    rows = rows.filter(r => (Number(r.estimated_amount) || 0) <= filters.amount_max)
  }
  return rows
})

function onFilterChange() {
  const f = {}
  if (filters.status) f.status = filters.status
  setFilters(f)
  searchGrs(null, f)
}

function handleReset() {
  Object.assign(filters, { status: '', amount_min: null, amount_max: null })
  resetFilters()
  searchGrs()
}

function handlePageChange(page) { onPageChange(page); searchGrs() }
function handleSizeChange(size) { onPageSizeChange(size); searchGrs() }

onMounted(() => searchGrs())
</script>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/ScListView.vue frontend/src/views/PoListView.vue frontend/src/views/GrListView.vue
git commit -m "feat: add list views — ScListView, PoListView, GrListView"
```

---

### Task 12: Detail views — ScDetailView, PoDetailView + remaining list views

**Files:**
- Create: `frontend/src/views/ScDetailView.vue`
- Create: `frontend/src/views/PoDetailView.vue`
- Create: `frontend/src/views/VendorListView.vue`
- Create: `frontend/src/views/LogsView.vue`

```vue
<template>
  <div>
    <div class="detail-page-header">
      <div>
        <h2>{{ detail.sc?.sc_no || detail.sc?.sc_id || 'SC Detail' }}</h2>
        <p>
          <StatusBadge v-if="detail.sc" :status="detail.sc.status" />
          <span v-if="detail.sc" style="color:#94a3b8;margin-left:8px">{{ detail.sc.request_type }}</span>
        </p>
      </div>
      <div class="header-actions">
        <el-button v-if="permissions.can_edit_sc" @click="openEditDialog">Edit</el-button>
        <el-button v-if="permissions.can_submit_sc" type="primary" @click="handleSubmit">Submit</el-button>
        <el-button v-if="permissions.can_approve_sc" type="success" @click="handleApprove">Approve</el-button>
        <el-button v-if="permissions.can_deny_sc" type="warning" @click="handleDeny">Deny</el-button>
        <el-button v-if="permissions.can_close_sc" type="danger" @click="handleClose">Close</el-button>
      </div>
    </div>

    <div v-if="state.detailLoading" class="section-card">
      <el-skeleton :rows="5" animated />
    </div>

    <el-alert v-if="state.detailError" :title="state.detailError" type="error" show-icon style="margin-bottom:16px" />

    <template v-if="detail.sc">
      <div class="section-card">
        <div class="section-header">
          <h3>SC Information</h3>
        </div>
        <ScDetailCard :sc="detail.sc" />
      </div>

      <div class="section-card">
        <div class="section-header">
          <h3>PO Records</h3>
          <el-button v-if="permissions.can_manage_po" type="primary" size="small" @click="poDialogVisible = true; poDialogMode = 'create'; poDialogRecord = null">
            <el-icon><Plus /></el-icon> Add PO
          </el-button>
        </div>
        <PoTable
          :rows="detail.pos || []"
          @row-click="row => $router.push(`/sc/${scId}/po/${row.po_id}`)"
          @edit="row => { poDialogRecord = { ...row, sc_id: scId }; poDialogMode = 'edit'; poDialogVisible = true }"
          @approve="row => handlePoApprove(row)"
          @finish="row => handlePoFinish(row)"
        />
      </div>

      <div class="section-card">
        <h3>Audit</h3>
        <el-table :data="detail.audit_logs || []" stripe border size="small">
          <el-table-column prop="created_at" label="Created" width="160">
            <template #default="{ row }">{{ row.created_at?.slice(0,19) }}</template>
          </el-table-column>
          <el-table-column prop="action_type" label="Action" width="140" />
          <el-table-column prop="object_type" label="Object" width="100" />
          <el-table-column prop="object_id" label="Object ID" width="120" />
          <el-table-column prop="operator_id" label="Operator" width="120" />
          <el-table-column prop="machine_id" label="Machine" min-width="120" />
          <template #empty><el-empty description="No audit records." /></template>
        </el-table>
      </div>
    </template>

    <ScFormDialog
      v-model:visible="editDialogVisible"
      mode="edit"
      :record="detail.sc"
      :users="activeUsers"
      @save-submit="handleEditSave"
    />

    <PoFormDialog
      v-model:visible="poDialogVisible"
      :mode="poDialogMode"
      :record="poDialogRecord"
      :vendors="vendors"
      @save="handlePoSave"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Plus } from '@element-plus/icons-vue'
import { useSc } from '@/composables/useSc.js'
import { usePo } from '@/composables/usePo.js'
import { useVendor } from '@/composables/useVendor.js'
import { callApi } from '@/api/bridge.js'
import StatusBadge from '@/components/common/StatusBadge.vue'
import ScDetailCard from '@/components/sc/ScDetailCard.vue'
import ScFormDialog from '@/components/sc/ScFormDialog.vue'
import PoTable from '@/components/po/PoTable.vue'
import PoFormDialog from '@/components/po/PoFormDialog.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const { state, fetchDetail, updateSc, submitSc, approveSc, denySc, closeSc } = useSc()
const { createPo, updatePo, approvePo, finishPo } = usePo()
const { state: vendorState, searchVendors } = useVendor()

const scId = computed(() => route.params.id)
const detail = computed(() => state.detail || {})
const permissions = computed(() => detail.value.permissions || {})
const vendors = computed(() => vendorState.rows)
const activeUsers = ref([])

const editDialogVisible = ref(false)
const poDialogVisible = ref(false)
const poDialogMode = ref('create')
const poDialogRecord = ref(null)

function openEditDialog() { editDialogVisible.value = true }

async function handleEditSave(data) {
  try {
    await updateSc(data)
    ElMessage.success('SC updated')
    await fetchDetail(scId.value)
  } catch (e) { ElMessage.error(e.message); throw e }
}

async function handleSubmit() {
  try {
    await ElMessageBox.confirm('Submit this SC?', 'Confirm', { type: 'warning' })
    await submitSc({ sc_id: scId.value })
    ElMessage.success('SC submitted')
    await fetchDetail(scId.value)
  } catch { /* cancelled */ }
}

async function handleApprove() {
  try {
    await ElMessageBox.confirm('Approve this SC?', 'Confirm', { type: 'warning' })
    await approveSc(scId.value)
    ElMessage.success('SC approved')
    await fetchDetail(scId.value)
  } catch { /* cancelled */ }
}

async function handleDeny() {
  try {
    await ElMessageBox.confirm('Deny this SC?', 'Confirm', { type: 'warning' })
    await denySc(scId.value)
    ElMessage.success('SC denied')
    await fetchDetail(scId.value)
  } catch { /* cancelled */ }
}

async function handleClose() {
  try {
    await ElMessageBox.prompt('Type "I CONFIRM CLOSE THIS SC" to proceed.', 'Close SC', {
      confirmButtonText: 'Close',
      type: 'warning',
      inputPattern: /^I CONFIRM CLOSE THIS SC$/,
      inputErrorMessage: 'Type the confirmation text exactly.'
    })
    await closeSc(scId.value)
    ElMessage.success('SC closed')
    await fetchDetail(scId.value)
  } catch { /* cancelled */ }
}

async function handlePoApprove(row) {
  try {
    await ElMessageBox.confirm('Approve this PO?', 'Confirm', { type: 'warning' })
    await approvePo(row.po_id)
    ElMessage.success('PO approved')
    await fetchDetail(scId.value)
  } catch { /* cancelled */ }
}

async function handlePoFinish(row) {
  try {
    await ElMessageBox.confirm('Finish this PO?', 'Confirm', { type: 'warning' })
    await finishPo(row.po_id)
    ElMessage.success('PO finished')
    await fetchDetail(scId.value)
  } catch { /* cancelled */ }
}

async function handlePoSave(data) {
  try {
    if (poDialogMode.value === 'create') {
      await createPo({ ...data, sc_id: scId.value })
    } else {
      await updatePo(data)
    }
    ElMessage.success('Saved')
    await fetchDetail(scId.value)
    poDialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
}

onMounted(async () => {
  try { activeUsers.value = await callApi('list_users') } catch {}
  await Promise.all([fetchDetail(scId.value), searchVendors()])
})

watch(() => route.params.id, async (newId) => {
  if (newId) await fetchDetail(newId)
})
</script>

<style scoped>
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.section-header h3 {
  font-size: 15px;
  font-weight: 600;
}
.header-actions {
  display: flex;
  gap: 6px;
}
</style>
```

- [ ] **Step 2: Create PoDetailView.vue**

```vue
<template>
  <div>
    <div class="detail-page-header">
      <div>
        <h2>{{ po.po_no || po.po_id || 'PO Detail' }}</h2>
        <p><StatusBadge v-if="po.status" :status="po.status" /></p>
      </div>
      <div class="header-actions">
        <el-button v-if="scDetail?.permissions?.can_manage_po" @click="openEditDialog">Edit</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_po && po.status === 'po_pending'" type="success" @click="handleApprove">Approve</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_po && po.status === 'po_approved'" type="info" @click="handleFinish">Finish</el-button>
      </div>
    </div>

    <div v-if="!po.po_id" class="section-card">
      <el-empty description="PO not found." />
    </div>

    <template v-if="po.po_id">
      <div class="section-card">
        <h3 style="margin-bottom:12px">PO Information</h3>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="PO ID">{{ po.po_id }}</el-descriptions-item>
          <el-descriptions-item label="PO No">{{ po.po_no || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Vendor">{{ po.vendor_name || po.vendor_id }}</el-descriptions-item>
          <el-descriptions-item label="PO Amount"><AmountDisplay :value="po.po_amount" /></el-descriptions-item>
          <el-descriptions-item label="Contract From">{{ po.contract_from?.slice(0,10) || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Contract To">{{ po.contract_to?.slice(0,10) || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Contract No">{{ po.contract_no || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Payment Freq">{{ po.payment_frequency || '-' }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <div class="section-card">
        <div class="section-header">
          <h3>GR Records</h3>
          <el-button v-if="scDetail?.permissions?.can_manage_gr" type="primary" size="small" @click="grDialogVisible = true; grDialogMode = 'create'; grDialogRecord = null">
            <el-icon><Plus /></el-icon> Add GR
          </el-button>
        </div>
        <GrTable
          :rows="grs"
          @edit="row => { grDialogRecord = { ...row, po_id: poId }; grDialogMode = 'edit'; grDialogVisible = true }"
          @approve="row => handleGrApprove(row)"
          @cancel="row => handleGrCancel(row)"
        />
      </div>
    </template>

    <PoFormDialog
      v-model:visible="editDialogVisible"
      mode="edit"
      :record="po"
      :vendors="vendors"
      @save="handleEditSave"
    />

    <GrFormDialog
      v-model:visible="grDialogVisible"
      :mode="grDialogMode"
      :record="grDialogRecord"
      @save="handleGrSave"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Plus } from '@element-plus/icons-vue'
import { useSc } from '@/composables/useSc.js'
import { usePo } from '@/composables/usePo.js'
import { useGr } from '@/composables/useGr.js'
import { useVendor } from '@/composables/useVendor.js'
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'
import PoFormDialog from '@/components/po/PoFormDialog.vue'
import GrTable from '@/components/po/GrTable.vue'
import GrFormDialog from '@/components/po/GrFormDialog.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const { state: scState, fetchDetail } = useSc()
const { updatePo, approvePo, finishPo } = usePo()
const { createGr, updateGr, approveGr, cancelGr } = useGr()
const { state: vendorState, searchVendors } = useVendor()

const scId = computed(() => route.params.scId)
const poId = computed(() => route.params.poId)
const scDetail = computed(() => scState.detail)
const po = computed(() => {
  const pos = scDetail.value?.pos || []
  return pos.find(p => String(p.po_id) === String(poId.value)) || {}
})
const grs = computed(() => {
  const allGrs = scDetail.value?.grs || []
  return allGrs.filter(g => String(g.po_id) === String(poId.value))
})
const vendors = computed(() => vendorState.rows)

const editDialogVisible = ref(false)
const grDialogVisible = ref(false)
const grDialogMode = ref('create')
const grDialogRecord = ref(null)

function openEditDialog() { editDialogVisible.value = true }

async function handleEditSave(data) {
  try {
    await updatePo(data)
    ElMessage.success('PO updated')
    await fetchDetail(scId.value)
  } catch (e) { ElMessage.error(e.message); throw e }
}

async function handleApprove() {
  try {
    await ElMessageBox.confirm('Approve this PO?', 'Confirm', { type: 'warning' })
    await approvePo(poId.value)
    ElMessage.success('PO approved')
    await fetchDetail(scId.value)
  } catch {}
}

async function handleFinish() {
  try {
    await ElMessageBox.confirm('Finish this PO?', 'Confirm', { type: 'warning' })
    await finishPo(poId.value)
    ElMessage.success('PO finished')
    await fetchDetail(scId.value)
  } catch {}
}

async function handleGrApprove(row) {
  try {
    await ElMessageBox.confirm('Approve this GR?', 'Confirm', { type: 'warning' })
    await approveGr(row.gr_id)
    ElMessage.success('GR approved')
    await fetchDetail(scId.value)
  } catch {}
}

async function handleGrCancel(row) {
  try {
    await ElMessageBox.confirm('Cancel this GR?', 'Confirm', { type: 'warning' })
    await cancelGr(row.gr_id)
    ElMessage.success('GR cancelled')
    await fetchDetail(scId.value)
  } catch {}
}

async function handleGrSave(data) {
  try {
    if (grDialogMode.value === 'create') {
      await createGr({ ...data, po_id: poId.value })
    } else {
      await updateGr(data)
    }
    ElMessage.success('Saved')
    await fetchDetail(scId.value)
    grDialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
}

onMounted(async () => {
  await Promise.all([fetchDetail(scId.value), searchVendors()])
})
</script>
```

- [ ] **Step 3: Create VendorListView.vue**

```vue
<template>
  <div>
    <FilterBar @reset="handleReset">
      <template #filters>
        <el-select v-model="filters.service_scope" placeholder="Service Scope" clearable @change="onFilterChange">
          <el-option v-for="s in serviceScopes" :key="s" :label="s" :value="s" />
        </el-select>
        <el-input v-model="filters.text" placeholder="Vendor name / KSRM code" clearable @change="onFilterChange" style="width:220px" />
      </template>
      <template #actions>
        <el-button type="primary" @click="dialogVisible = true; dialogMode = 'create'">
          <el-icon><Plus /></el-icon> Add Vendor
        </el-button>
      </template>
    </FilterBar>

    <el-table :data="filteredRows" v-loading="state.loading" stripe border>
      <el-table-column prop="vendor_name" label="Vendor" sortable="custom" min-width="160" />
      <el-table-column prop="ksrm_vendor_code" label="KSRM Code" width="110" />
      <el-table-column prop="service_scope" label="Service Scope" width="180" />
      <el-table-column prop="contact_person" label="Contact" width="110" />
      <el-table-column prop="phone" label="Phone" width="120" />
      <el-table-column prop="email" label="Email" min-width="160">
        <template #default="{ row }">{{ row.email || '-' }}</template>
      </el-table-column>
      <el-table-column label="Actions" width="140" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="dialogVisible = true; dialogMode = 'edit'; dialogRecord = row">Edit</el-button>
          <el-popconfirm title="Disable this vendor?" @confirm="handleDisable(row)">
            <template #reference>
              <el-button type="danger" link size="small">Disable</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty><el-empty :description="state.error || 'No vendors found.'" /></template>
    </el-table>

    <VendorFormDialog
      v-model:visible="dialogVisible"
      :mode="dialogMode"
      :record="dialogRecord"
      @save="handleSave"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { useVendor } from '@/composables/useVendor.js'
import FilterBar from '@/components/common/FilterBar.vue'
import VendorFormDialog from '@/components/vendor/VendorFormDialog.vue'
import { ElMessage } from 'element-plus'

const { state, searchVendors, createVendor, updateVendor, disableVendor } = useVendor()

const serviceScopes = [
  'Transportation', 'engineering Service', 'Equipment', 'Parts', 'Driver',
  'Test car rental', 'General Service', 'Dealers', 'Import&Export&cusoms clearance',
  'Insurance', 'Harness', 'Maintenance', 'Security', 'Testing support', 'Others'
]

const filters = reactive({ service_scope: '', text: '' })
const dialogVisible = ref(false)
const dialogMode = ref('create')
const dialogRecord = ref(null)

const filteredRows = computed(() => {
  let rows = state.rows
  if (filters.service_scope) {
    rows = rows.filter(r => r.service_scope === filters.service_scope)
  }
  if (filters.text) {
    const t = filters.text.toLowerCase()
    rows = rows.filter(r =>
      (r.vendor_name || '').toLowerCase().includes(t) ||
      (r.ksrm_vendor_code || '').toLowerCase().includes(t)
    )
  }
  return rows
})

function onFilterChange() { /* client-side filters, no server re-fetch needed */ }
function handleReset() { Object.assign(filters, { service_scope: '', text: '' }) }

async function handleSave(data) {
  try {
    if (dialogMode.value === 'create') {
      await createVendor(data)
    } else {
      await updateVendor(data.vendor_id, data)
    }
    dialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
}

async function handleDisable(row) {
  try {
    await disableVendor(row.vendor_id)
    ElMessage.success('Vendor disabled')
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(() => searchVendors())
</script>
```

- [ ] **Step 4: Create LogsView.vue**

```vue
<template>
  <div>
    <FilterBar @reset="handleReset">
      <template #filters>
        <el-date-picker v-model="filters.created_at" type="date" placeholder="Date" value-format="YYYY-MM-DD" @change="onFilterChange" />
        <el-input v-model="filters.action_type" placeholder="Action type" clearable @change="onFilterChange" style="width:160px" />
      </template>
    </FilterBar>

    <el-table :data="filteredRows" v-loading="state.loading" stripe border>
      <el-table-column prop="created_at" label="Created" width="160" sortable="custom">
        <template #default="{ row }">{{ row.created_at?.slice(0,19) }}</template>
      </el-table-column>
      <el-table-column prop="action_type" label="Action" width="150" />
      <el-table-column prop="object_type" label="Object" width="100" />
      <el-table-column prop="object_id" label="Object ID" width="130" />
      <el-table-column prop="sc_id" label="SC ID" width="130" />
      <el-table-column prop="operator_id" label="Operator" width="130" />
      <el-table-column prop="machine_id" label="Machine" min-width="130" />
      <template #empty><el-empty :description="state.error || 'No audit logs found.'" /></template>
    </el-table>

    <el-pagination
      v-if="state.total > state.pageSize"
      :current-page="state.currentPage"
      :page-size="state.pageSize"
      :total="state.total"
      layout="total, sizes, prev, pager, next, jumper"
      @current-change="handlePageChange"
      @size-change="handleSizeChange"
      style="margin-top:12px;justify-content:flex-end"
    />
  </div>
</template>

<script setup>
import { reactive, computed, onMounted } from 'vue'
import { useLogs } from '@/composables/useLogs.js'
import FilterBar from '@/components/common/FilterBar.vue'

const { state, searchLogs, setFilters, resetFilters, onPageChange, onPageSizeChange } = useLogs()

const filters = reactive({ created_at: '', action_type: '' })

const filteredRows = computed(() => {
  let rows = state.rows
  if (filters.created_at) {
    rows = rows.filter(r => (r.created_at || '').startsWith(filters.created_at))
  }
  if (filters.action_type) {
    const t = filters.action_type.toLowerCase()
    rows = rows.filter(r => (r.action_type || '').toLowerCase().includes(t))
  }
  return rows
})

function onFilterChange() {
  const f = {}
  if (filters.action_type) f.action_type = filters.action_type
  setFilters(f)
  searchLogs(null, f)
}

function handleReset() {
  Object.assign(filters, { created_at: '', action_type: '' })
  resetFilters()
  searchLogs()
}

function handlePageChange(page) { onPageChange(page); searchLogs() }
function handleSizeChange(size) { onPageSizeChange(size); searchLogs() }

onMounted(() => searchLogs())
</script>
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/ScDetailView.vue frontend/src/views/PoDetailView.vue frontend/src/views/VendorListView.vue frontend/src/views/LogsView.vue
git commit -m "feat: add detail views and Vendor/Logs list views"
```

---

### Task 13: HomeView (Workbench) + SystemView

**Files:**
- Create: `frontend/src/views/HomeView.vue`
- Create: `frontend/src/views/SystemView.vue`

- [ ] **Step 1: Create HomeView.vue**

```vue
<template>
  <div>
    <h2 style="margin-bottom:16px;font-size:20px;font-weight:700">Workbench</h2>
    <el-row :gutter="16">
      <el-col :span="12" v-for="card in cards" :key="card.title" style="margin-bottom:16px">
        <el-card shadow="hover" class="workbench-card">
          <template #header>
            <div class="card-header">
              <span>{{ card.title }}</span>
              <el-button type="primary" link size="small" @click="card.link">
                View all <el-icon><ArrowRight /></el-icon>
              </el-button>
            </div>
          </template>
          <el-table :data="card.rows" size="small" @row-click="card.onRowClick" style="cursor:pointer">
            <el-table-column prop="status" label="Status" width="100">
              <template #default="{ row }"><StatusBadge :status="row.status" /></template>
            </el-table-column>
            <el-table-column :prop="card.idKey" :label="card.idLabel" min-width="120" />
            <el-table-column :prop="card.amountKey" :label="card.amountLabel" width="110">
              <template #default="{ row }"><AmountDisplay :value="row[card.amountKey]" /></template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!card.rows.length" :description="'No ' + card.title" :image-size="40" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight } from '@element-plus/icons-vue'
import { callApi } from '@/api/bridge.js'
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'

const router = useRouter()
const user = computed(() => window.__currentUser || {})
const isAdmin = computed(() => user.value?.role === 'admin')

const pendingScs = ref([])
const pendingPos = ref([])
const pendingGrs = ref([])
const drafts = ref([])
const deniedScs = ref([])

const cards = computed(() => {
  if (isAdmin.value) {
    return [
      { title: 'Pending SCs', rows: pendingScs.value.slice(0, 5), idKey: 'sc_no', idLabel: 'SC No', amountKey: 'sc_amount', amountLabel: 'Amount', link: () => router.push('/sc'), onRowClick: row => router.push(`/sc/${row.sc_id}`) },
      { title: 'Pending POs', rows: pendingPos.value.slice(0, 5), idKey: 'po_no', idLabel: 'PO No', amountKey: 'po_amount', amountLabel: 'Amount', link: () => router.push('/po'), onRowClick: row => router.push(`/sc/${row.sc_id}/po/${row.po_id}`) },
      { title: 'Pending GRs', rows: pendingGrs.value.slice(0, 5), idKey: 'gr_id', idLabel: 'GR ID', amountKey: 'estimated_amount', amountLabel: 'Estimated', link: () => router.push('/gr'), onRowClick: row => router.push(`/sc/${row.sc_id}/po/${row.po_id}`) },
      { title: 'My Drafts', rows: drafts.value.slice(0, 5), idKey: 'sc_id', idLabel: 'SC ID', amountKey: 'sc_amount', amountLabel: 'Amount', link: () => router.push('/sc'), onRowClick: row => router.push(`/sc/${row.sc_id}`) }
    ]
  }
  return [
    { title: 'My Pending SCs', rows: pendingScs.value.slice(0, 5), idKey: 'sc_no', idLabel: 'SC No', amountKey: 'sc_amount', amountLabel: 'Amount', link: () => router.push('/sc'), onRowClick: row => router.push(`/sc/${row.sc_id}`) },
    { title: 'My Drafts', rows: drafts.value.slice(0, 5), idKey: 'sc_id', idLabel: 'SC ID', amountKey: 'sc_amount', amountLabel: 'Amount', link: () => router.push('/sc'), onRowClick: () => {} },
    { title: 'Denied SCs', rows: deniedScs.value.slice(0, 5), idKey: 'sc_no', idLabel: 'SC No', amountKey: 'sc_amount', amountLabel: 'Amount', link: () => router.push('/sc'), onRowClick: row => router.push(`/sc/${row.sc_id}`) },
    { title: 'Active POs', rows: pendingPos.value.slice(0, 5), idKey: 'po_no', idLabel: 'PO No', amountKey: 'po_amount', amountLabel: 'Amount', link: () => router.push('/po'), onRowClick: row => router.push(`/sc/${row.sc_id}/po/${row.po_id}`) }
  ]
})

onMounted(async () => {
  try {
    const [scResult, poResult, grResult] = await Promise.all([
      callApi('search_scs', { filters: { status: 'pending' }, limit: 5, offset: 0 }),
      callApi('search_pos', { filters: { status: 'po_pending' }, limit: 5, offset: 0 }),
      callApi('search_grs', { filters: { status: 'pending' }, limit: 5, offset: 0 })
    ])
    pendingScs.value = scResult.rows || scResult
    pendingPos.value = poResult.rows || poResult
    pendingGrs.value = grResult.rows || grResult
  } catch {}
  try {
    const draftResult = await callApi('search_scs', { filters: { status: 'draft' }, limit: 5, offset: 0 })
    drafts.value = draftResult.rows || draftResult
  } catch {}
  try {
    const deniedResult = await callApi('search_scs', { filters: { status: 'denied' }, limit: 5, offset: 0 })
    deniedScs.value = deniedResult.rows || deniedResult
  } catch {}
})
</script>

<style scoped>
.workbench-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}
</style>
```

- [ ] **Step 2: Create SystemView.vue**

```vue
<template>
  <div>
    <div class="section-card">
      <h3 style="margin-bottom:12px">Current User</h3>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="Machine ID">{{ user?.machine_id }}</el-descriptions-item>
        <el-descriptions-item label="Name">{{ user?.user_name }}</el-descriptions-item>
        <el-descriptions-item label="Role"><el-tag size="small" :type="user?.role === 'admin' ? 'danger' : ''">{{ user?.role }}</el-tag></el-descriptions-item>
        <el-descriptions-item label="Email">{{ user?.email || '-' }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <div v-if="isAdmin" class="section-card">
      <div class="section-header">
        <h3>User Management</h3>
        <el-button type="primary" size="small" @click="dialogVisible = true; dialogMode = 'create'; dialogRecord = null">
          <el-icon><Plus /></el-icon> Add User
        </el-button>
      </div>
      <el-table :data="state.users" v-loading="state.loading" stripe border>
        <el-table-column prop="machine_id" label="Machine ID" width="120" />
        <el-table-column prop="user_name" label="Name" width="160" />
        <el-table-column prop="email" label="Email" min-width="180" />
        <el-table-column prop="role" label="Role" width="100" />
        <el-table-column label="Status" width="100">
          <template #default="{ row }"><StatusBadge :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="Actions" width="160" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="dialogVisible = true; dialogMode = 'edit'; dialogRecord = row">Edit</el-button>
            <el-popconfirm v-if="row.status === 'active'" title="Disable this user?" @confirm="handleDisable(row)">
              <template #reference><el-button type="danger" link size="small">Disable</el-button></template>
            </el-popconfirm>
            <el-popconfirm v-else title="Enable this user?" @confirm="handleEnable(row)">
              <template #reference><el-button type="success" link size="small">Enable</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
        <template #empty><el-empty description="No users found." /></template>
      </el-table>
    </div>

    <UserFormDialog
      v-model:visible="dialogVisible"
      :mode="dialogMode"
      :record="dialogRecord"
      @save="handleSave"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { useUser } from '@/composables/useUser.js'
import StatusBadge from '@/components/common/StatusBadge.vue'
import UserFormDialog from '@/components/system/UserFormDialog.vue'
import { ElMessage } from 'element-plus'

const { state, fetchUsers, createUser, updateUser, disableUser, enableUser } = useUser()

const user = computed(() => window.__currentUser || {})
const isAdmin = computed(() => user.value?.role === 'admin')

const dialogVisible = ref(false)
const dialogMode = ref('create')
const dialogRecord = ref(null)

async function handleSave(data) {
  try {
    if (dialogMode.value === 'create') {
      await createUser(data)
    } else {
      await updateUser(data.machine_id, data)
    }
    dialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
}

async function handleDisable(row) {
  try {
    await disableUser(row.machine_id)
    ElMessage.success('User disabled')
  } catch (e) { ElMessage.error(e.message) }
}

async function handleEnable(row) {
  try {
    await enableUser(row.machine_id)
    ElMessage.success('User enabled')
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(async () => {
  if (isAdmin.value) await fetchUsers()
})
</script>
```

- [ ] **Step 3: Verify build runs successfully**

```bash
cd frontend && npm run build
```

Expected: Build succeeds. Output in `sc_gr_app/web/` with `index.html`, `assets/` directory.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/HomeView.vue frontend/src/views/SystemView.vue
git commit -m "feat: add HomeView (workbench) and SystemView (user management)"
```

---

### Task 14: Backend additions — Vendor CRUD + enable_user

**Files:**
- Modify: `sc_gr_app/services/vendor_service.py`
- Modify: `sc_gr_app/services/user_service.py`
- Modify: `sc_gr_app/api/bridge.py`

- [ ] **Step 1: Add update_vendor and disable_vendor to vendor_service.py**

Add these functions at the end of `sc_gr_app/services/vendor_service.py`:

```python
def update_vendor(config: AppConfig, current_user: dict, vendor_id: str, data: dict) -> dict:
    require_requester_or_admin(current_user)
    with LeaseLock(config.lock_dir, "system", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_vendor(conn, vendor_id)
                if not before:
                    raise ValidationError(f"Vendor {vendor_id} not found")

                timestamp = utc_now()
                fields = [
                    "vendor_name", "ksrm_vendor_code", "contact_person", "phone",
                    "service_scope", "email", "description", "inquiry_history"
                ]
                for field in fields:
                    if field in data:
                        conn.execute(
                            f"update vendors set {field} = ?, updated_at = ? where vendor_id = ?",
                            (data[field], timestamp, vendor_id)
                        )

                if "service_scope" in data and data["service_scope"] not in SUPPORTED_SERVICE_SCOPES:
                    raise ValidationError("service_scope is invalid")

                after = _get_vendor(conn, vendor_id)
                write_audit_log(
                    conn,
                    action_type="update_vendor",
                    object_type="vendor",
                    object_id=vendor_id,
                    sc_id=None,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=after,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    return after


def disable_vendor(config: AppConfig, current_user: dict, vendor_id: str) -> dict:
    require_requester_or_admin(current_user)
    with LeaseLock(config.lock_dir, "system", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_vendor(conn, vendor_id)
                if not before:
                    raise ValidationError(f"Vendor {vendor_id} not found")
                timestamp = utc_now()
                conn.execute(
                    "update vendors set status = 'disabled', updated_at = ? where vendor_id = ?",
                    (timestamp, vendor_id)
                )
                after = _get_vendor(conn, vendor_id)
                write_audit_log(
                    conn,
                    action_type="disable_vendor",
                    object_type="vendor",
                    object_id=vendor_id,
                    sc_id=None,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=after,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    return after
```

- [ ] **Step 2: Add enable_user to user_service.py**

Add at the end of `sc_gr_app/services/user_service.py`:

```python
def enable_user(config: AppConfig, current_user: dict, machine_id: str) -> dict:
    if current_user.get("role") != "admin":
        raise PermissionDenied("Only admins can enable users")
    with connect(config) as conn:
        row = conn.execute(
            "select * from users where machine_id = ? and status = 'disabled'",
            (machine_id,),
        ).fetchone()
        if not row:
            raise NotFound(f"Disabled user with machine_id {machine_id} not found")
        before = dict(row)
        timestamp = now()
        conn.execute(
            "update users set status = 'active', updated_at = ? where machine_id = ?",
            (timestamp, machine_id),
        )
        after = {**before, "status": "active", "updated_at": timestamp}
        write_audit_log(
            conn,
            action_type="enable_user",
            object_type="user",
            object_id=before["user_id"],
            sc_id=None,
            operator_id=current_user["user_id"],
            machine_id=current_user["machine_id"],
            before=before,
            after=after,
        )
        conn.commit()
    return after
```

- [ ] **Step 3: Expose new methods in bridge.py**

Add these methods to `ApiBridge` class in `sc_gr_app/api/bridge.py`:

```python
def create_vendor(self, payload) -> dict:
    require_requester_or_admin(self.current_user)
    return ok(vendor_service.create_vendor(self.config, self.current_user, payload["data"]))

def update_vendor(self, payload) -> dict:
    require_requester_or_admin(self.current_user)
    return ok(vendor_service.update_vendor(self.config, self.current_user, payload["vendor_id"], payload["data"]))

def disable_vendor(self, payload) -> dict:
    require_requester_or_admin(self.current_user)
    return ok(vendor_service.disable_vendor(self.config, self.current_user, payload["vendor_id"]))

def enable_user(self, payload) -> dict:
    require_requester_or_admin(self.current_user)
    return ok(enable_user(self.config, self.current_user, payload["machine_id"]))
```

Also add the import for `enable_user` at the top of bridge.py:
```python
from sc_gr_app.services.user_service import seed_default_admin, get_user_by_machine_id, list_active_users, create_user, update_user, disable_user, enable_user
```

- [ ] **Step 4: Run existing tests to verify no regressions**

```bash
uv run pytest -q
```

Expected: All existing tests pass.

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/services/vendor_service.py sc_gr_app/services/user_service.py sc_gr_app/api/bridge.py
git commit -m "feat: add vendor CRUD and enable_user backend endpoints"
```

---

### Task 15: Desktop features — app_shell.py, tray, update check

**Files:**
- Modify: `sc_gr_app/__init__.py` — add `__version__`
- Rewrite: `sc_gr_app/app_shell.py` — WebView2, dev mode, mutex, tray, update check
- Create: `sc_gr_app/icons/tray.ico` — tray icon (copy from existing icons or generate)

- [ ] **Step 1: Add version to __init__.py**

```python
__version__ = "2.0.0"
```

- [ ] **Step 2: Rewrite app_shell.py**

```python
import ctypes
import os
import sys
import threading
from pathlib import Path

import webview
from webview.platforms.edgechromium import EdgeChrome

from sc_gr_app import __version__
from sc_gr_app.api.bridge import ApiBridge
from sc_gr_app.config import default_config
from sc_gr_app.db.migrations import migrate
from sc_gr_app.services.user_service import seed_users

MUTEX_NAME = "Local\\SC_GR_MANAGEMENT_INSTANCE"
WINDOW_TITLE = "SC GR Management"
DEV_MODE = os.getenv("SC_GR_DEV") == "1"
MIN_WIDTH, MIN_HEIGHT = 1100, 700
DEFAULT_WIDTH, DEFAULT_HEIGHT = 1280, 820


def _patch_webview2():
    _original = EdgeChrome.on_webview_ready
    def _patched(self, sender, args):
        _original(self, sender, args)
        if not args.IsSuccess:
            return
        settings = sender.CoreWebView2.Settings
        settings.AreBrowserAcceleratorKeysEnabled = False
        settings.AreDefaultContextMenusEnabled = True
        settings.AreDevToolsEnabled = DEV_MODE
    EdgeChrome.on_webview_ready = _patched


def _single_instance_check():
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() != 183:
        return
    hwnd = ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE)
    if hwnd:
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.ShowWindow(hwnd, 9)
    sys.exit(0)


def _webview2_storage():
    base = Path(os.getenv("LOCALAPPDATA") or Path.home()) / "sc-gr-management" / "webview2"
    base.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("WEBVIEW2_USER_DATA_FOLDER", str(base))
    return base


def _check_update(window):
    """Async check for updates on startup. Fail silently if unreachable."""
    # Placeholder — replace UPDATE_URL with actual update server
    return
    import requests
    try:
        resp = requests.get("UPDATE_URL/latest-version.txt", timeout=3)
        latest = resp.text.strip()
        if latest > __version__:
            window.evaluate_js(f"window.__updateAvailable = {{ version: '{latest}' }}")
    except Exception:
        pass


def _setup_tray(window):
    """Minimize to tray on close. Tray icon with context menu."""
    try:
        from pystray import Icon, Menu, MenuItem
        from PIL import Image
    except ImportError:
        return

    icon_path = Path(__file__).parent / "icons" / "tray.png"
    if not icon_path.exists():
        return

    image = Image.open(icon_path)

    def show_window(icon, item):
        window.show()
        window.restore()

    def exit_app(icon, item):
        icon.stop()
        window.destroy()
        os._exit(0)

    icon = Icon("sc-gr-mgmt", image, WINDOW_TITLE, Menu(
        MenuItem("Show Window", show_window, default=True),
        MenuItem("Exit", exit_app)
    ))

    def _on_closing():
        window.hide()

    window.events.closing += _on_closing

    threading.Thread(target=icon.run, daemon=True).start()
    return icon


def run_app():
    _single_instance_check()
    _patch_webview2()

    config = default_config()
    migrate(config)
    seed_users(config)

    html_path = Path(__file__).parent / "web" / "index.html"
    storage_path = _webview2_storage()
    bridge = ApiBridge(config)

    if DEV_MODE:
        url = "http://localhost:5173"
    else:
        url = f"file://{html_path}"

    window = webview.create_window(
        WINDOW_TITLE,
        url=url,
        js_api=bridge,
        width=DEFAULT_WIDTH,
        height=DEFAULT_HEIGHT,
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        text_select=True,
    )

    _check_update(window)
    _setup_tray(window)

    webview.start(debug=DEV_MODE)
```

- [ ] **Step 3: Run the app and verify dev mode works**

```bash
$env:SC_GR_DEV="1"
cd frontend && npm run dev &
uv run python -m sc_gr_app.main
```

Expected: App window opens, loads from localhost:5173, Vue dev tools available.

- [ ] **Step 4: Build production and verify file:// loading works**

```bash
cd frontend && npm run build
$env:SC_GR_DEV="0"
uv run python -m sc_gr_app.main
```

Expected: App window opens, loads from built files in sc_gr_app/web/.

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/__init__.py sc_gr_app/app_shell.py
git commit -m "feat: add desktop features — WebView2, single instance, tray, dev mode"
```

---

### Task 16: Polish — CSS, tray icon, cleanup old files

**Files:**
- Create: `sc_gr_app/icons/tray.png` — 16x16 or 32x32 PNG for system tray
- Delete: old `sc_gr_app/web/` files after build validation
- Modify: `frontend/src/assets/main.css` — final polish

- [ ] **Step 1: Create tray icon**

Copy one of the existing PNG icons (e.g., from `sc_gr_app/web/icons/`) as `sc_gr_app/icons/tray.png`.

```bash
cp sc_gr_app/web/icons/*.png sc_gr_app/icons/tray.png 2>/dev/null || echo "Create a 32x32 PNG for tray icon manually"
```

Or use a placeholder: any 32x32 PNG file at `sc_gr_app/icons/tray.png`.

- [ ] **Step 2: Add el-table row status bar styles to main.css**

Append to `frontend/src/assets/main.css`:

```css
/* Compact table */
.el-table td, .el-table th {
  padding: 8px 10px;
}

/* Section spacing */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.section-header h3 {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
}

/* Detail page header spacing */
.header-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

/* Scrollbar styling */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
```

- [ ] **Step 3: Rebuild and verify final build**

```bash
cd frontend && npm run build
ls sc_gr_app/web/
```

Expect: `index.html`, `assets/` directory with JS and CSS bundles.

- [ ] **Step 4: Remove old web/ source files (keep built output and icons)**

```bash
rm sc_gr_app/web/app.js
rm sc_gr_app/web/styles.css
rm -rf sc_gr_app/web/components/
```

The `sc_gr_app/web/` directory should now contain only:
- `index.html` (Vite output)
- `assets/` (Vite output — JS/CSS bundles)
- `icons/` (PNG icon files used by Vue components)

- [ ] **Step 5: Final commit**

```bash
git add -A sc_gr_app/icons/ sc_gr_app/web/index.html sc_gr_app/web/assets/
git add -u sc_gr_app/web/
git add frontend/src/assets/main.css
git commit -m "feat: polish UI styles, tray icon, clean up old frontend files"
```

---

### Task 17: Final integration test

- [ ] **Step 1: Run all Python tests**

```bash
uv run pytest -q
```

Expected: All tests pass. No regressions from backend changes.

- [ ] **Step 2: Verify app launches in production mode**

```bash
$env:SC_GR_DEV="0"
uv run python -m sc_gr_app.main
```

Expected: Login screen appears, user can verify identity and enter. All views render from built files.

- [ ] **Step 3: Smoke test key flows**

Manual verification:
1. Login → Workbench loads with dashboard cards
2. SC List → filter, search, "New SC" dialog, row click → SC Detail
3. SC Detail → SC info, PO table, "Add PO" dialog
4. PO Detail → PO info, GR table, "Add GR" dialog
5. Vendor List → "Add Vendor" dialog, edit, disable
6. System → user management (admin only)
7. Close window → minimizes to tray
8. Tray icon → "Show Window" restores, "Exit" closes

- [ ] **Step 4: Commit any fixups**

```bash
git add -A
git commit -m "fix: integration test fixes"
```

