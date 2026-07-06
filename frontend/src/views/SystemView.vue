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
      <el-collapse v-model="userCollapseActive">
        <el-collapse-item :title="$t('user.userList') + ' (' + filteredUsers.length + ')'" name="user-table">
          <el-input
            v-model="userSearch"
            :placeholder="$t('user.searchUsers')"
            clearable
            style="width:280px;margin-bottom:12px"
            size="small"
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-table :data="filteredUsers" v-loading="state.loading" stripe border>
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
        </el-collapse-item>
      </el-collapse>
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

    <div v-if="isAdmin" class="section-card">
      <div class="section-header">
        <h3>{{ $t('settings.senderEmail') }}</h3>
      </div>
      <div style="display:flex;align-items:center;gap:8px">
        <el-input v-model="senderEmail" :placeholder="'VGC.RS-POMP@audi.com'" style="flex:1" />
        <el-button type="primary" :disabled="senderEmail === savedSenderEmail" @click="handleSaveSenderEmail">
          {{ $t('common.save') }}
        </el-button>
      </div>
      <p style="color:#94a3b8;font-size:12px;margin-top:8px">{{ $t('settings.senderEmailHint') }}</p>
    </div>

    <div v-if="isAdmin" class="section-card">
      <div class="section-header">
        <h3>{{ $t('record.recordLogs') }}</h3>
        <el-button size="small" @click="handleLogsExport" :loading="logsExporting">
          <el-icon><Download /></el-icon> {{ $t('common.export') }}
        </el-button>
      </div>
      <el-collapse v-model="logsCollapseActive">
        <el-collapse-item :title="$t('record.recordLogs') + ' (' + logsState.total + ')'" name="logs-table">
          <AdvancedFilterBar
            :filter-config="logsFilterConfig"
            @filter="handleLogsFilter"
            @reset="handleLogsReset"
          />
          <el-table :data="logsState.rows" v-loading="logsState.loading" stripe border style="margin-top:12px">
            <el-table-column prop="created_at" :label="$t('record.created')" width="160" sortable="custom">
              <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column prop="action_type" :label="$t('record.action')" width="150" />
            <el-table-column prop="object_type" :label="$t('record.object')" width="100" />
            <el-table-column prop="object_id" :label="$t('record.objectId')" width="130" />
            <el-table-column prop="sc_id" :label="$t('record.scId')" width="130" />
            <el-table-column prop="operator_id" :label="$t('record.operator')" width="130" />
            <el-table-column prop="machine_id" :label="$t('record.machine')" min-width="130" />
            <template #empty><el-empty :description="logsState.error || $t('record.noRecords')" /></template>
          </el-table>
          <el-pagination
            :current-page="logsState.currentPage"
            :page-size="logsState.pageSize"
            :total="logsState.total"
            layout="total, sizes, prev, pager, next, jumper"
            @current-change="handleLogsPageChange"
            @size-change="handleLogsSizeChange"
            style="margin-top:12px;justify-content:flex-end"
          />
        </el-collapse-item>
      </el-collapse>
    </div>

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
import { Plus, Download, Search } from '@element-plus/icons-vue'
import { callApi } from '@/api/bridge.js'
import { useUser } from '@/composables/useUser.js'
import { useExport } from '@/composables/useExport.js'
import { formatDateTime } from '@/utils/format.js'
import StatusBadge from '@/components/common/StatusBadge.vue'
import UserFormDialog from '@/components/system/UserFormDialog.vue'
import { useLogs } from '@/composables/useLogs.js'
import AdvancedFilterBar from '@/components/common/AdvancedFilterBar.vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const { state, fetchUsers, createUser, updateUser, disableUser, enableUser } = useUser()
const { exportRows } = useExport()
const exporting = ref(false)

const user = computed(() => window.__currentUser || {})
const isAdmin = computed(() => user.value?.role === 'admin')

const dialogVisible = ref(false)
const dialogMode = ref('create')
const dialogRecord = ref(null)

const userSearch = ref('')
const userCollapseActive = ref([])
const logsCollapseActive = ref([])

const filteredUsers = computed(() => {
  if (!userSearch.value) return state.users
  const q = userSearch.value.toLowerCase()
  return (state.users || []).filter(u =>
    (u.machine_id && u.machine_id.toLowerCase().includes(q)) ||
    (u.user_name && u.user_name.toLowerCase().includes(q)) ||
    (u.email && u.email.toLowerCase().includes(q)) ||
    (u.role && u.role.toLowerCase().includes(q))
  )
})

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

const { state: logsState, searchLogs, setFilters: setLogsFilters, resetFilters: resetLogsFilters, onPageChange: onLogsPageChange, onPageSizeChange: onLogsSizeChange } = useLogs()
const { exportAll } = useExport()
const logsExporting = ref(false)

const logsFilterConfig = [
  { name: 'action_type', label: t('record.action'), type: 'input' },
  { name: 'object_type', label: t('record.objectType'), type: 'input' },
  { name: 'object_id', label: t('record.objectId'), type: 'input' },
  { name: 'sc_id', label: t('record.scId'), type: 'input' },
  { name: 'operator_id', label: t('record.operator'), type: 'input' },
  { name: 'machine_id', label: t('record.machine'), type: 'input' },
  { name: 'operation_mode', label: t('record.mode'), type: 'input' },
]

function handleLogsFilter({ text, filters }) {
  searchLogs(text, filters)
}

function handleLogsReset() {
  resetLogsFilters()
  searchLogs()
}

function handleLogsPageChange(page) { onLogsPageChange(page); searchLogs() }
function handleLogsSizeChange(size) { onLogsSizeChange(size); searchLogs() }

async function handleLogsExport() {
  logsExporting.value = true
  try {
    const columns = [
      { key: 'created_at', label: t('record.created'), getValue: r => formatDateTime(r.created_at) },
      { key: 'action_type', label: t('record.action') },
      { key: 'object_type', label: t('record.objectType') },
      { key: 'object_id', label: t('record.objectId') },
      { key: 'sc_id', label: t('record.scId') },
      { key: 'operator_id', label: t('record.operator') },
      { key: 'machine_id', label: t('record.machine') }
    ]
    await exportAll('search_operation_records', {
      filters: logsState.filters,
      sort: logsState.sort,
      direction: logsState.direction
    }, columns, `Operation_Records_${new Date().toISOString().slice(0, 10)}`)
    ElMessage.success(t('record.exportSuccess'))
  } catch (e) {
    ElMessage.error(e.message || t('record.exportFailed'))
  } finally {
    logsExporting.value = false
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

// ── Sender email ──
const senderEmail = ref('')
const savedSenderEmail = ref('')

async function fetchSenderEmail() {
  try {
    const result = await callApi('get_sender_email')
    senderEmail.value = result.email || ''
    savedSenderEmail.value = result.email || ''
  } catch { senderEmail.value = ''; savedSenderEmail.value = '' }
}

async function handleSaveSenderEmail() {
  try {
    const result = await callApi('set_sender_email', { email: senderEmail.value })
    savedSenderEmail.value = result.email
    ElMessage.success(t('common.saved'))
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(() => {
  if (isAdmin.value) { fetchUsers(); searchLogs() }
  fetchAttachmentsDir()
  fetchSenderEmail()
})
</script>
