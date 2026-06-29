<template>
  <div>
    <div class="section-card">
      <div class="section-header">
        <h3>{{ $t('email.emailNotifications') }}</h3>
        <el-button size="small" @click="$router.push('/emails')">
          <el-icon><ArrowLeft /></el-icon> {{ $t('email.backToSettings') }}
        </el-button>
      </div>
      <div style="display:flex;gap:12px;margin-bottom:12px">
        <el-select v-model="filters.status" :placeholder="$t('email.status')" clearable style="width:140px" @change="onFilterChange">
          <el-option :label="$t('email.pending')" value="pending" />
          <el-option :label="$t('email.sent')" value="sent" />
          <el-option :label="$t('email.failed')" value="failed" />
        </el-select>
        <el-select v-model="filters.entity_type" :placeholder="$t('email.type')" clearable style="width:120px" @change="onFilterChange">
          <el-option label="SC" value="sc" />
          <el-option label="PO" value="po" />
          <el-option label="GR" value="gr" />
        </el-select>
        <el-input v-model="filters.entity_id" :placeholder="$t('email.entityId')" clearable style="width:160px" @change="onFilterChange" />
        <el-button @click="handleRefresh" :loading="state.queueLoading">{{ $t('common.refresh') }}</el-button>
        <el-button @click="handleReset">{{ $t('common.reset') }}</el-button>
        <el-button @click="handleExport" :loading="exporting">
          <el-icon><Download /></el-icon> {{ $t('common.export') }}
        </el-button>
      </div>
    </div>

    <el-table :data="state.queue" v-loading="state.queueLoading" stripe border>
      <el-table-column prop="entity_type" :label="$t('email.type')" width="70">
        <template #default="{ row }">
          <el-tag size="small" :type="row.entity_type === 'sc' ? 'primary' : row.entity_type === 'po' ? 'warning' : 'info'">
            {{ row.entity_type.toUpperCase() }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="entity_id" :label="$t('email.entityId')" width="130" />
      <el-table-column prop="event_type" :label="$t('email.eventType')" width="130">
        <template #default="{ row }">
          <el-tag size="small" :type="row.event_type === 'status_change' ? 'primary' : 'warning'">
            {{ row.event_type === 'status_change' ? $t('email.eventStatus') : row.event_type === 'threshold_date' ? $t('email.eventDate') : $t('email.eventAmount') }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="event_key" :label="$t('email.event')" width="160" />
      <el-table-column :label="$t('email.to')" min-width="150">
        <template #default="{ row }">
          <span style="font-size:12px;color:#64748b">{{ formatRecipients(row.to_recipients) }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('email.cc')" min-width="150">
        <template #default="{ row }">
          <span style="font-size:12px;color:#64748b">{{ formatRecipients(row.cc_recipients) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="status" :label="$t('email.status')" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'sent' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" :label="$t('email.created')" width="160">
        <template #default="{ row }">{{ (row.created_at || '').replace('T', ' ').slice(0, 19) }}</template>
      </el-table-column>
      <el-table-column prop="sent_at" :label="$t('email.sent')" width="160">
        <template #default="{ row }">{{ (row.sent_at || '').replace('T', ' ').slice(0, 19) || '-' }}</template>
      </el-table-column>
      <el-table-column prop="error_msg" :label="$t('email.error')" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">{{ row.error_msg || '-' }}</template>
      </el-table-column>
      <el-table-column :label="$t('common.actions')" width="140" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.status !== 'sent'"
            type="primary" link size="small"
            @click="previewEntry = row; previewVisible = true"
          >{{ $t('email.previewSend') }}</el-button>
          <span v-else style="color:#94a3b8;font-size:12px">{{ $t('email.sent') }}</span>
        </template>
      </el-table-column>
      <template #empty><el-empty :description="state.queueError || $t('email.noRecords')" /></template>
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

    <EmailPreviewDialog v-model="previewVisible" :entry-id="previewEntry?.id" @sent="loadQueue" />
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Download, ArrowLeft } from '@element-plus/icons-vue'
import EmailPreviewDialog from '@/components/notification/EmailPreviewDialog.vue'
import { useNotification } from '@/composables/useNotification.js'
import { useExport } from '@/composables/useExport.js'
import { callApi } from '@/api/bridge.js'
import { ElMessage } from 'element-plus'

const { t } = useI18n()
const { state, fetchQueue } = useNotification()
const { exportAll } = useExport()
const pageSize = 50
const currentPage = ref(1)
const exporting = ref(false)
const previewVisible = ref(false)
const previewEntry = ref(null)

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
    entity_type: filters.entity_type || null,
    entity_id: filters.entity_id || null,
    limit: pageSize,
    offset: (currentPage.value - 1) * pageSize
  })
}

function handleReset() {
  filters.status = ''
  filters.entity_type = ''
  filters.entity_id = ''
  currentPage.value = 1
  loadQueue()
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
      { key: 'entity_type', label: t('email.type') },
      { key: 'entity_id', label: t('email.entityId') },
      { key: 'event_type', label: t('email.eventType') },
      { key: 'event_key', label: t('email.event') },
      { key: 'to_recipients', label: t('email.to'), getValue: r => formatRecipients(r.to_recipients) },
      { key: 'cc_recipients', label: t('email.cc'), getValue: r => formatRecipients(r.cc_recipients) },
      { key: 'status', label: t('email.status') },
      { key: 'created_at', label: t('email.created'), getValue: r => (r.created_at || '').replace('T', ' ').slice(0, 19) },
      { key: 'sent_at', label: t('email.sent'), getValue: r => (r.sent_at || '').replace('T', ' ').slice(0, 19) || '-' },
      { key: 'error_msg', label: t('email.error'), getValue: r => r.error_msg || '-' }
    ]
    await exportAll('list_notification_queue', {
      status: filters.status || null,
      entity_type: filters.entity_type || null,
      entity_id: filters.entity_id || null
    }, columns, `Email_Logs_${new Date().toISOString().slice(0, 10)}`)
    ElMessage.success(t('email.exportSuccess'))
  } catch (e) {
    ElMessage.error(e.message || t('email.exportFailed'))
  } finally {
    exporting.value = false
  }
}

onMounted(() => loadQueue())
</script>
