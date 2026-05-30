<template>
  <div class="login-screen">
    <el-card class="login-card" shadow="always">
      <h1 class="login-title">SC GR Operations</h1>
      <p class="login-subtitle">Budget & Purchase Order Management</p>

      <!-- Loading / Retrying state -->
      <div v-if="state === 'loading' || state === 'retrying'" class="login-state">
        <el-icon class="spinner" :size="32"><Loading /></el-icon>
        <p style="margin-top:16px;color:#64748b">{{ state === 'loading' ? 'Detecting identity...' : 'Retrying...' }}</p>
        <p v-if="lastError" style="color:#94a3b8;font-size:12px;margin-top:8px">{{ lastError }}</p>
        <p v-if="retryCount > 0" style="color:#94a3b8;font-size:11px;margin-top:4px">Attempt {{ retryCount }}</p>
      </div>

      <!-- Authorized state -->
      <div v-if="state === 'authorized'" class="login-state">
        <el-result icon="success" title="Identity Verified">
          <template #sub-title>
            <p>{{ user?.user_name }} <el-tag size="small" :type="user?.role === 'admin' ? 'danger' : 'info'">{{ user?.role }}</el-tag></p>
            <p style="color:#94a3b8;font-size:12px;">{{ user?.machine_id }}</p>
          </template>
          <template #extra>
            <el-button type="primary" size="large" @click="enterApp">Enter</el-button>
          </template>
        </el-result>
      </div>

      <!-- Unauthorized state (terminal, after retries exhausted) -->
      <div v-if="state === 'unauthorized'" class="login-state">
        <el-result icon="error" title="Not Authorized">
          <template #sub-title>
            <p>{{ lastError || 'This machine is not authorized to access the system.' }}</p>
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
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Loading } from '@element-plus/icons-vue'
import { callApi, ApiError } from '@/api/bridge.js'

const router = useRouter()
const state = ref('loading')
const user = ref(null)
const lastError = ref('')
const retryCount = ref(0)
const MAX_RETRIES = 10
let retryTimer = null

function stopRetry() {
  if (retryTimer) {
    clearTimeout(retryTimer)
    retryTimer = null
  }
}

async function verify() {
  stopRetry()
  if (state.value !== 'retrying') {
    state.value = 'loading'
  }
  lastError.value = ''

  try {
    user.value = await callApi('current_user')
    window.__currentUser = user.value
    state.value = 'authorized'
  } catch (e) {
    lastError.value = e.message || 'Unable to reach the database.'
    if (e instanceof ApiError && e.code === 'PERMISSION_DENIED') {
      state.value = 'unauthorized'
    } else if (retryCount.value >= MAX_RETRIES) {
      state.value = 'unauthorized'
      lastError.value = 'Server unreachable. Please check your connection and try again.'
    } else {
      state.value = 'retrying'
      retryCount.value++
      retryTimer = setTimeout(verify, 2000)
    }
  }
}

function enterApp() {
  stopRetry()
  const redirect = router.currentRoute.value.query?.redirect || '/workbench'
  router.push(redirect)
}

onMounted(verify)
onUnmounted(stopRetry)
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
.spinner {
  animation: spin 1s linear infinite;
  color: #3b82f6;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
