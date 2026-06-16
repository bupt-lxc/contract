<template>
  <div class="sidenav-container">
    <div class="sidenav-brand">
      <span v-if="!collapsed" class="brand-text">{{ $t('app.brand') }}</span>
      <span v-else class="brand-icon">{{ $t('app.brandShort') }}</span>
      <span v-if="isBeta" class="beta-indicator" :title="$t('app.betaLabel')">β</span>
      <span v-if="!collapsed && version" class="version-text">{{ version }}</span>
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
        <span>{{ $t('nav.workbench') }}</span>
      </el-menu-item>
      <el-menu-item index="/sc">
        <el-icon><Document /></el-icon>
        <span>{{ $t('nav.sc') }}</span>
      </el-menu-item>
      <el-menu-item index="/po">
        <el-icon><ShoppingCart /></el-icon>
        <span>{{ $t('nav.po') }}</span>
      </el-menu-item>
      <el-menu-item index="/gr">
        <el-icon><CircleCheck /></el-icon>
        <span>{{ $t('nav.gr') }}</span>
      </el-menu-item>
      <el-menu-item index="/vendor">
        <el-icon><OfficeBuilding /></el-icon>
        <span>{{ $t('nav.vendor') }}</span>
      </el-menu-item>
      <el-menu-item index="/emails">
        <el-icon><Message /></el-icon>
        <span>{{ $t('nav.email') }}</span>
      </el-menu-item>
      <el-menu-item v-if="isAdmin" index="/system">
        <el-icon><Setting /></el-icon>
        <span>{{ $t('nav.system') }}</span>
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
import { computed, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { callApi } from '@/api/bridge.js'
import {
  Monitor, Document, ShoppingCart, CircleCheck, OfficeBuilding,
  Message, Setting, DArrowLeft, DArrowRight
} from '@element-plus/icons-vue'

defineProps({
  collapsed: { type: Boolean, default: false }
})
defineEmits(['toggle'])

const route = useRoute()
const version = ref('')

const activeRoute = computed(() => {
  if (route.path.startsWith('/sc')) return '/sc'
  if (route.path.startsWith('/po')) return '/po'
  if (route.path.startsWith('/gr')) return '/gr'
  if (route.path.startsWith('/emails')) return '/emails'
  return route.path
})

const isAdmin = computed(() => window.__currentUser?.role === 'admin')
const isBeta = computed(() => !!window.__isBeta)

onMounted(async () => {
  try {
    version.value = await callApi('get_version')
  } catch {
    // version not critical — silently ignore
  }
})
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
.beta-indicator {
  font-size: 11px;
  color: #f59e0b;
  margin-left: 6px;
  font-weight: 700;
}
.version-text {
  font-size: 11px;
  color: #94a3b8;
  margin-left: 6px;
  font-weight: 400;
}
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
