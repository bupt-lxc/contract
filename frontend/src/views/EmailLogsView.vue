<template>
  <div>
    <div class="section-card">
      <div class="section-header">
        <h3>Email Notifications</h3>
      </div>
      <div style="display:flex;gap:12px;margin-bottom:12px">
        <el-select v-model="filters.status" placeholder="Status" clearable style="width:140px" @change="onFilterChange">
          <el-option label="Pending" value="pending" />
          <el-option label="Sent" value="sent" />
          <el-option label="Failed" value="failed" />
        </el-select>
        <el-select v-model="filters.entity_type" placeholder="Type" clearable style="width:120px" @change="onFilterChange">
          <el-option label="SC" value="sc" />
          <el-option label="PO" value="po" />
          <el-option label="GR" value="gr" />
        </el-select>
        <el-input v-model="filters.entity_id" placeholder="Entity ID" clearable style="width:160px" @change="onFilterChange" />
        <el-button @click="handleRefresh" :loading="state.queueLoading">Refresh</el-button>
        <el-button @click="handleExport" :loading="exporting">
          <el-icon><Download /></el-icon> Export
        </el-button>
      </div>
    </div>

    <el-table :data="state.queue" v-loading="state.queueLoading" stripe border>
      <el-table-column prop="entity_type" label="Type" width="70">
        <template #default="{ row }">
          <el-tag size="small" :type="row.entity_type === 'sc' ? '' : row.entity_type === 'po' ? 'warning' : 'info'">
            {{ row.entity_type.toUpperCase() }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="entity_id" label="Entity ID" width="130" />
      <el-table-column prop="event_type" label="Event Type" width="130">
        <template #default="{ row }">
          <el-tag size="small" :type="row.event_type === 'status_change' ? 'primary' : 'warning'">
            {{ row.event_type === 'status_change' ? 'Status' : row.event_type === 'threshold_date' ? 'Date' : 'Amount' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="event_key" label="Event" width="160" />
      <el-table-column label="To" min-width="150">
        <template #default="{ row }">
          <span style="font-size:12px;color:#64748b">{{ formatRecipients(row.to_recipients) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="CC" min-width="150">
        <template #default="{ row }">
          <span style="font-size:12px;color:#64748b">{{ formatRecipients(row.cc_recipients) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="Status" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'sent' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="Created" width="160">
        <template #default="{ row }">{{ (row.created_at || '').slice(0, 19) }}</template>
      </el-table-column>
      <el-table-column prop="sent_at" label="Sent" width="160">
        <template #default="{ row }">{{ (row.sent_at || '').slice(0, 19) || '-' }}</template>
      </el-table-column>
      <el-table-column prop="error_msg" label="Error" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">{{ row.error_msg || '-' }}</template>
      </el-table-column>
      <template #empty><el-empty :description="state.queueError || 'No email notifications found.'" /></template>
    </el-table>

    <el-pagination
      v-if="state.queueTotal > pageSize"
      v-model:current-page="currentPage"
      :page-size="pageSize"
      :total="state.queueTotal"
      layout="total, prev, pager, next"
      @current-change="handlePageChange"
      style="margin-top:12px;justify-content:flex-end"
    />
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { useNotification } from '@/composables/useNotification.js'
import { useExport } from '@/composables/useExport.js'
import { callApi } from '@/api/bridge.js'
import { ElMessage } from 'element-plus'

const { state, fetchQueue } = useNotification()
const { exportAll } = useExport()
const pageSize = 50
const currentPage = ref(1)
const exporting = ref(false)

const filters = reactive({
  status: '',
  entity_type: '',
  entity_id: ''
})

function formatRecipients(jsonStr) {
  try {
    const ids = JSON.parse(jsonStr)
    return ids.length ? ids.join(', ') : '-'
  } catch {
    return jsonStr || '-'
  }
}

function loadQueue() {
  fetchQueue({
    status: filters.status || null,
    limit: pageSize,
    offset: (currentPage.value - 1) * pageSize
  })
}

function onFilterChange() {
  currentPage.value = 1
  loadQueue()
}

function handleRefresh() {
  loadQueue()
}

function handlePageChange(page) {
  currentPage.value = page
  loadQueue()
}

async function handleExport() {
  exporting.value = true
  try {
    const columns = [
      { key: 'entity_type', label: 'Type' },
      { key: 'entity_id', label: 'Entity ID' },
      { key: 'event_type', label: 'Event Type' },
      { key: 'event_key', label: 'Event' },
      { key: 'to_recipients', label: 'To', getValue: r => formatRecipients(r.to_recipients) },
      { key: 'cc_recipients', label: 'CC', getValue: r => formatRecipients(r.cc_recipients) },
      { key: 'status', label: 'Status' },
      { key: 'created_at', label: 'Created', getValue: r => (r.created_at || '').slice(0, 19) },
      { key: 'sent_at', label: 'Sent', getValue: r => (r.sent_at || '').slice(0, 19) || '-' },
      { key: 'error_msg', label: 'Error', getValue: r => r.error_msg || '-' }
    ]
    await exportAll('list_notification_queue', {
      status: filters.status || null,
      entity_type: filters.entity_type || null,
      entity_id: filters.entity_id || null
    }, columns, `Email_Logs_${new Date().toISOString().slice(0, 10)}`)
    ElMessage.success('Exported successfully')
  } catch (e) {
    ElMessage.error(e.message || 'Export failed')
  } finally {
    exporting.value = false
  }
}

onMounted(() => loadQueue())
</script>
