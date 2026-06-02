<template>
  <div>
    <div class="section-card">
      <h3 style="margin-bottom:12px">{{ $t('user.currentUser') }}</h3>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="Machine ID">{{ user?.machine_id }}</el-descriptions-item>
        <el-descriptions-item label="Name">{{ user?.user_name }}</el-descriptions-item>
        <el-descriptions-item label="Role"><el-tag size="small" :type="user?.role === 'admin' ? 'danger' : 'info'">{{ user?.role }}</el-tag></el-descriptions-item>
        <el-descriptions-item label="Email">{{ user?.email || '-' }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <div v-if="isAdmin" class="section-card">
      <div class="section-header">
        <h3>{{ $t('user.userManagement') }}</h3>
        <el-button type="primary" size="small" @click="dialogVisible = true; dialogMode = 'create'; dialogRecord = null">
          <el-icon><Plus /></el-icon> {{ $t('user.addUser') }}
        </el-button>
        <el-button size="small" @click="handleExport" :loading="exporting">
          <el-icon><Download /></el-icon> {{ $t('common.export') }}
        </el-button>
      </div>
      <el-table :data="state.users" v-loading="state.loading" stripe border>
        <el-table-column prop="machine_id" :label="$t('user.machineId')" width="120" />
        <el-table-column prop="user_name" :label="$t('user.name')" width="160" />
        <el-table-column prop="email" :label="$t('user.email')" min-width="180" />
        <el-table-column prop="role" :label="$t('user.role')" width="100" />
        <el-table-column :label="$t('user.status')" width="100">
          <template #default="{ row }"><StatusBadge :status="row.status" /></template>
        </el-table-column>
        <el-table-column :label="$t('common.actions')" width="160" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="dialogVisible = true; dialogMode = 'edit'; dialogRecord = row">{{ $t('common.edit') }}</el-button>
            <el-popconfirm v-if="row.status === 'active'" :title="$t('user.disableConfirm')" @confirm="handleDisable(row)">
              <template #reference><el-button type="danger" link size="small">{{ $t('common.disable') }}</el-button></template>
            </el-popconfirm>
            <el-popconfirm v-else :title="$t('user.enableConfirm')" @confirm="handleEnable(row)">
              <template #reference><el-button type="success" link size="small">{{ $t('common.enable') }}</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
        <template #empty><el-empty :description="$t('common.noData')" /></template>
      </el-table>
    </div>

    <div v-if="isAdmin" class="section-card">
      <div class="section-header">
        <h3>{{ $t('settings.attachmentsDir') }}</h3>
      </div>
      <div style="display:flex;align-items:center;gap:8px">
        <el-input :model-value="attachmentsDir" readonly style="flex:1" />
        <el-button @click="handlePickFolder">{{ $t('common.browse') }}</el-button>
        <el-button type="primary" :disabled="!pendingAttachmentsDir || pendingAttachmentsDir === attachmentsDir" @click="handleSaveAttachmentsDir">
          {{ $t('common.save') }}
        </el-button>
      </div>
      <p style="color:#94a3b8;font-size:12px;margin-top:8px">{{ $t('settings.attachmentsDirHint') }}</p>
    </div>

    <NotificationDefaults
      v-if="isAdmin"
      :defaults="notifState.defaults"
      :loading="notifState.defaultsLoading"
      :users="state.users"
      @save="handleNotifDefaultsSave"
    />

    <UserFormDialog
      v-model:visible="dialogVisible"
      :mode="dialogMode"
      :record="dialogRecord"
      @save="handleSave"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Plus, Download } from '@element-plus/icons-vue'
import { callApi } from '@/api/bridge.js'
import { useUser } from '@/composables/useUser.js'
import { useExport } from '@/composables/useExport.js'
import StatusBadge from '@/components/common/StatusBadge.vue'
import UserFormDialog from '@/components/system/UserFormDialog.vue'
import NotificationDefaults from '@/components/notification/NotificationDefaults.vue'
import { useNotification } from '@/composables/useNotification.js'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const { state, fetchUsers, createUser, updateUser, disableUser, enableUser } = useUser()
const { state: notifState, fetchDefaults, saveDefaults } = useNotification()
const { exportRows } = useExport()
const exporting = ref(false)

const user = computed(() => window.__currentUser || {})
const isAdmin = computed(() => user.value?.role === 'admin')

const dialogVisible = ref(false)
const dialogMode = ref('create')
const dialogRecord = ref(null)

async function handleSave(data) {
  try {
    if (dialogMode.value === 'create') {
      await createUser(data)
    } else {
      await updateUser(data.machine_id, data)
    }
    ElMessage.success(t('common.saved'))
    dialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
}

async function handleDisable(row) {
  try {
    await disableUser(row.machine_id)
    ElMessage.success(t('user.userDisabled'))
  } catch (e) { ElMessage.error(e.message) }
}

async function handleEnable(row) {
  try {
    await enableUser(row.machine_id)
    ElMessage.success(t('user.userEnabled'))
  } catch (e) { ElMessage.error(e.message) }
}

async function handleExport() {
  exporting.value = true
  try {
    const columns = [
      { key: 'machine_id', label: t('user.machineId') },
      { key: 'user_name', label: t('user.name') },
      { key: 'email', label: t('user.email') },
      { key: 'role', label: t('user.role') },
      { key: 'status', label: t('user.status') }
    ]
    await exportRows(state.users, columns, `Users_${new Date().toISOString().slice(0, 10)}`)
    ElMessage.success(t('common.exportSuccess'))
  } catch (e) {
    ElMessage.error(e.message || t('common.exportFailed'))
  } finally {
    exporting.value = false
  }
}

async function handleNotifDefaultsSave(data) {
  try {
    await saveDefaults(data)
    ElMessage.success(t('notification.defaultsSaved'))
  } catch (e) {
    ElMessage.error(t('notification.defaultsSaveFailed'))
  }
}

// ── Attachments directory ──
const attachmentsDir = ref('')
const pendingAttachmentsDir = ref('')

async function fetchAttachmentsDir() {
  try {
    const result = await callApi('get_attachments_dir')
    attachmentsDir.value = result.path || ''
    pendingAttachmentsDir.value = ''
  } catch { attachmentsDir.value = '' }
}

async function handlePickFolder() {
  try {
    const result = await callApi('pick_folder')
    if (result.cancelled) return
    pendingAttachmentsDir.value = result.path
  } catch (e) { ElMessage.error(e.message) }
}

async function handleSaveAttachmentsDir() {
  if (!pendingAttachmentsDir.value) return
  try {
    await callApi('set_attachments_dir', { path: pendingAttachmentsDir.value })
    attachmentsDir.value = pendingAttachmentsDir.value
    pendingAttachmentsDir.value = ''
    ElMessage.success(t('common.saved'))
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(() => {
  if (isAdmin.value) fetchUsers()
  fetchDefaults()
  fetchAttachmentsDir()
})
</script>
