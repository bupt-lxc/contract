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
