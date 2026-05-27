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
