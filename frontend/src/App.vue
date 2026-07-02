<template>
  <AppLoadingBar />
  <UpdateDialog
    :visible="!!updateInfo"
    :version="updateInfo?.version || ''"
    :changelog="updateInfo?.changelog_cn || ''"
    :loading="updating"
    @install="handleInstallUpdate"
  />
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
import AppLoadingBar from '@/components/common/AppLoadingBar.vue'
import UpdateDialog from '@/components/system/UpdateDialog.vue'
import { callApi } from '@/api/bridge.js'
import { ElMessage } from 'element-plus'

const route = useRoute()
const sidebarCollapsed = ref(false)

const updateInfo = ref(null)
const updating = ref(false)

window.__updateAvailable = (info) => {
  updateInfo.value = info
}

const layout = computed(() => route.meta?.layout || 'default')

async function handleInstallUpdate() {
  updating.value = true
  try {
    await callApi('install_update', {
      version: updateInfo.value.version,
      installer_name: updateInfo.value.installer_name,
      sha256: updateInfo.value.sha256
    })
  } catch (e) {
    ElMessage.error(e.message || 'Update failed')
    updating.value = false
  }
}

onMounted(() => {
  if (window.__isBeta) {
    document.title = 'PO Management Platform Beta'
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
