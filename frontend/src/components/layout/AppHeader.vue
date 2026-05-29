<template>
  <div class="header-left">
    <span class="header-title">SC GR Operations</span>
    <el-breadcrumb separator="/">
      <el-breadcrumb-item
        v-for="(item, index) in breadcrumbs"
        :key="index"
        :to="index < breadcrumbs.length - 1 ? item.to : undefined"
      >
        {{ item.title }}
      </el-breadcrumb-item>
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

const user = computed(() => window.__currentUser || null)

const breadcrumbs = computed(() => {
  const name = route.name
  const params = route.params

  const map = {
    'workbench': [
      { title: 'Workbench', to: '/workbench' }
    ],
    'sc-list': [
      { title: 'SC List', to: '/sc' }
    ],
    'sc-detail': [
      { title: 'SC List', to: '/sc' },
      { title: 'SC Detail', to: '' }
    ],
    'po-list': [
      { title: 'PO List', to: '/po' }
    ],
    'po-detail': [
      { title: 'SC List', to: '/sc' },
      { title: 'SC Detail', to: `/sc/${params.scId}` },
      { title: 'PO Detail', to: '' }
    ],
    'gr-list': [
      { title: 'GR List', to: '/gr' }
    ],
    'vendor-list': [
      { title: 'Vendor List', to: '/vendor' }
    ],
    'logs': [
      { title: 'Audit Logs', to: '/logs' }
    ],
    'emails': [
      { title: 'Email Logs', to: '/emails' }
    ],
    'system': [
      { title: 'System', to: '/system' }
    ]
  }
  return map[name] || []
})

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
