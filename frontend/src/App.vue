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
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import SideNav from '@/components/layout/SideNav.vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import LoginView from '@/views/LoginView.vue'

const route = useRoute()
const sidebarCollapsed = ref(false)

const layout = computed(() => route.meta?.layout || 'default')

onMounted(() => {
  if (window.__isBeta) {
    document.title = 'SC GR Management Beta'
  }
})
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
