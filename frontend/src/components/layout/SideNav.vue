<template>
  <div class="sidenav-container">
    <div class="sidenav-brand">
      <span v-if="!collapsed" class="brand-text">{{ $t('app.brand') }}</span>
      <span v-else class="brand-icon">{{ $t('app.brandShort') }}</span>
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
      <el-menu-item index="/logs">
        <el-icon><Notebook /></el-icon>
        <span>{{ $t('nav.logs') }}</span>
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
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  Monitor, Document, ShoppingCart, CircleCheck, OfficeBuilding,
  Message, Notebook, Setting, DArrowLeft, DArrowRight
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
