<template>
  <div class="login-screen">
    <el-card class="login-card" shadow="always">
      <h1 class="login-title">
        {{ $t('login.title') }}
        <el-tag v-if="isBeta" type="warning" size="small" class="beta-tag">{{ $t('app.betaLabel') }}</el-tag>
      </h1>
      <p class="login-subtitle">{{ $t('login.subtitle') }}</p>

      <!-- Loading / Retrying state -->
      <div v-if="state === 'loading' || state === 'retrying'" class="login-state">
        <el-icon class="spinner" :size="32"><Loading /></el-icon>
        <p style="margin-top:16px;color:#64748b">{{ state === 'loading' ? $t('login.detecting') : $t('login.retrying') }}</p>
        <p v-if="lastError" style="color:#94a3b8;font-size:12px;margin-top:8px">{{ lastError }}</p>
        <p v-if="retryCount > 0" style="color:#94a3b8;font-size:11px;margin-top:4px">{{ $t('login.attempt', { count: retryCount }) }}</p>
      </div>

      <!-- Authorized state -->
      <div v-if="state === 'authorized'" class="login-state">
        <!-- Dev mode role selector -->
        <div v-if="isDev" class="dev-role-select">
          <el-result icon="success" :title="$t('login.identityVerified')">
            <template #sub-title>
              <p>{{ user?.user_name }}</p>
              <p style="color:#94a3b8;font-size:12px;">{{ user?.machine_id }}</p>
            </template>
          </el-result>
          <p class="dev-role-hint">{{ $t('login.selectRole') }}</p>
          <div class="dev-role-cards">
            <div class="dev-role-card admin" @click="selectDevRole('admin')">
              <el-icon :size="32"><Setting /></el-icon>
              <span class="dev-role-label">{{ $t('login.adminPanel') }}</span>
              <span class="dev-role-desc">{{ $t('login.adminPanelDesc') }}</span>
            </div>
            <div class="dev-role-card requester" @click="selectDevRole('requester')">
              <el-icon :size="32"><User /></el-icon>
              <span class="dev-role-label">{{ $t('login.requesterPanel') }}</span>
              <span class="dev-role-desc">{{ $t('login.requesterPanelDesc') }}</span>
            </div>
          </div>
        </div>

        <!-- Normal authorized state -->
        <el-result v-else icon="success" :title="$t('login.identityVerified')">
          <template #sub-title>
            <p>{{ user?.user_name }} <el-tag size="small" :type="user?.role === 'admin' ? 'danger' : 'info'">{{ user?.role }}</el-tag></p>
            <p style="color:#94a3b8;font-size:12px;">{{ user?.machine_id }}</p>
          </template>
          <template #extra>
            <el-button type="primary" size="large" @click="enterApp">{{ $t('common.enter') }}</el-button>
          </template>
        </el-result>
      </div>

      <!-- Dev role selected — enter app -->
      <div v-if="state === 'role_selected'" class="login-state">
        <el-result icon="success" :title="$t('login.identityVerified')">
          <template #sub-title>
            <p>{{ user?.user_name }} <el-tag size="small" :type="user?.role === 'admin' ? 'danger' : 'info'">{{ $t(`role.${user?.role}`, user?.role) }}</el-tag></p>
            <p style="color:#94a3b8;font-size:12px;">{{ user?.machine_id }}</p>
          </template>
          <template #extra>
            <el-button type="primary" size="large" @click="enterApp">{{ $t('common.enter') }}</el-button>
            <br/>
            <el-button type="info" size="small" text @click="backToRoleSelect">{{ $t('login.switchRole') }}</el-button>
          </template>
        </el-result>
      </div>

      <!-- Unauthorized state (terminal, after retries exhausted) -->
      <div v-if="state === 'unauthorized'" class="login-state">
        <el-result icon="error" :title="$t('login.notAuthorized')">
          <template #sub-title>
            <p>{{ lastError || $t('login.notAuthorizedMsg') }}</p>
            <p style="color:#94a3b8;font-size:12px;margin-top:8px;">{{ $t('login.contactAdmin') }}</p>
          </template>
          <template #extra>
            <el-button @click="verify">{{ $t('common.retry') }}</el-button>
          </template>
        </el-result>
      </div>
    </el-card>
    <p class="login-version">{{ $t('app.version') }}</p>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { Loading, Setting, User } from '@element-plus/icons-vue'
import { callApi, ApiError } from '@/api/bridge.js'

const router = useRouter()
const { t } = useI18n()
const state = ref('loading')  // loading | retrying | authorized | role_selected | unauthorized
const user = ref(null)
const isDev = ref(false)
const isBeta = ref(false)
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
    try {
      isDev.value = await callApi('is_dev')
    } catch {
      isDev.value = false
    }
    try {
      isBeta.value = await callApi('is_beta')
      window.__isBeta = isBeta.value
    } catch {
      isBeta.value = false
      window.__isBeta = false
    }
    if (isBeta.value) {
      document.title = 'PO Management Platform Beta'
    }
    state.value = 'authorized'
  } catch (e) {
    lastError.value = e.message || t('login.unableToReach')
    if (e instanceof ApiError && e.code === 'PERMISSION_DENIED') {
      state.value = 'unauthorized'
    } else if (retryCount.value >= MAX_RETRIES) {
      state.value = 'unauthorized'
      lastError.value = t('login.serverUnreachable')
    } else {
      state.value = 'retrying'
      retryCount.value++
      retryTimer = setTimeout(verify, 2000)
    }
  }
}

async function selectDevRole(role) {
  try {
    user.value = await callApi('switch_dev_role', { role })
    window.__currentUser = user.value
    state.value = 'role_selected'
  } catch (e) {
    lastError.value = e.message
  }
}

function backToRoleSelect() {
  state.value = 'authorized'
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
.beta-tag {
  vertical-align: middle;
  margin-left: 8px;
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
.dev-role-select {
  text-align: center;
}
.dev-role-hint {
  font-size: 14px;
  color: #475569;
  margin-bottom: 16px;
  font-weight: 500;
}
.dev-role-cards {
  display: flex;
  gap: 16px;
  justify-content: center;
}
.dev-role-card {
  width: 160px;
  padding: 24px 12px;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  transition: all 0.2s;
  color: #475569;
}
.dev-role-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}
.dev-role-card.admin:hover {
  border-color: #ef4444;
  color: #ef4444;
}
.dev-role-card.requester:hover {
  border-color: #3b82f6;
  color: #3b82f6;
}
.dev-role-label {
  font-size: 16px;
  font-weight: 600;
}
.dev-role-desc {
  font-size: 11px;
  color: #94a3b8;
  text-align: center;
}
</style>
