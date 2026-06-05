<template>
  <div class="header-left">
    <span class="header-title">{{ $t('app.title') }}</span>
    <el-breadcrumb separator="/">
      <el-breadcrumb-item
        v-for="(item, index) in breadcrumbs"
        :key="index"
        :to="index < breadcrumbs.length - 1 ? item.to : undefined"
      >
        {{ $t(item.i18nKey) }}
      </el-breadcrumb-item>
    </el-breadcrumb>
  </div>
  <div class="header-right">
    <LocaleSwitcher />
    <el-dropdown trigger="click">
      <span class="user-info">
        {{ user?.user_name || $t('common.user') }}
        <el-tag size="small" :type="user?.role === 'admin' ? 'danger' : 'info'">{{ $t(`role.${user?.role}`, user?.role) }}</el-tag>
      </span>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item @click="handleLogout">{{ $t('common.exit') }}</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import LocaleSwitcher from './LocaleSwitcher.vue'

const route = useRoute()
const router = useRouter()

const user = computed(() => window.__currentUser || null)

const breadcrumbs = computed(() => {
  const name = route.name
  const params = route.params

  const map = {
    'workbench': [
      { i18nKey: 'breadcrumb.workbench', to: '/workbench' }
    ],
    'sc-list': [
      { i18nKey: 'breadcrumb.scList', to: '/sc' }
    ],
    'sc-detail': [
      { i18nKey: 'breadcrumb.scList', to: '/sc' },
      { i18nKey: 'breadcrumb.scDetail', to: '' }
    ],
    'po-list': [
      { i18nKey: 'breadcrumb.poList', to: '/po' }
    ],
    'po-detail': [
      { i18nKey: 'breadcrumb.scList', to: '/sc' },
      { i18nKey: 'breadcrumb.scDetail', to: `/sc/${params.scId}` },
      { i18nKey: 'breadcrumb.poDetail', to: '' }
    ],
    'gr-detail': [
      { i18nKey: 'breadcrumb.scList', to: '/sc' },
      { i18nKey: 'breadcrumb.scDetail', to: `/sc/${params.scId}` },
      { i18nKey: 'breadcrumb.poDetail', to: `/sc/${params.scId}/po/${params.poId}` },
      { i18nKey: 'breadcrumb.grDetail', to: '' }
    ],
    'gr-list': [
      { i18nKey: 'breadcrumb.grList', to: '/gr' }
    ],
    'vendor-list': [
      { i18nKey: 'breadcrumb.vendorList', to: '/vendor' }
    ],
    'logs': [
      { i18nKey: 'breadcrumb.auditLogs', to: '/logs' }
    ],
    'emails': [
      { i18nKey: 'breadcrumb.emailSettings', to: '/emails' }
    ],
    'emails-logs': [
      { i18nKey: 'breadcrumb.emailSettings', to: '/emails' },
      { i18nKey: 'breadcrumb.emailLogs', to: '/emails/logs' }
    ],
    'system': [
      { i18nKey: 'breadcrumb.system', to: '/system' }
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
