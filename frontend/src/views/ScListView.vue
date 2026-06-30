<template>
  <div>
    <AdvancedFilterBar
      :filter-config="scFilterConfig"
      @filter="handleFilter"
      @reset="handleReset"
    >
      <template #actions>
        <el-button type="primary" :disabled="loadingState.count > 0" @click="scDialogVisible = true; scDialogMode = 'create'">
          <el-icon><Plus /></el-icon> {{ $t('sc.newSc') }}
        </el-button>
        <el-button :disabled="loadingState.count > 0" @click="importVisible = true">
          <el-icon><Upload /></el-icon> Import
        </el-button>
        <el-button :disabled="loadingState.count > 0" @click="downloadTemplate">
          <el-icon><Download /></el-icon> Template
        </el-button>
        <el-button @click="handleExport" :loading="exporting">
          <el-icon><Download /></el-icon> {{ $t('common.export') }}
        </el-button>
      </template>
    </AdvancedFilterBar>

    <div v-if="selectedRows.length" style="margin-bottom:12px;display:flex;align-items:center;gap:12px;padding:8px 12px;background:#f0f9ff;border-radius:4px">
      <span style="font-size:13px;color:#1d4ed8;font-weight:500">{{ $t('batch.selected', { count: selectedRows.length }) }}</span>
      <el-button v-if="selectedRows.some(r => r.status === 'draft')" size="small" type="primary" :disabled="loadingState.count > 0" @click="handleBatchSubmit">{{ $t('batch.submit') }}</el-button>
      <el-button v-if="isAdmin && selectedRows.some(r => r.status === 'manager_confirm')" size="small" type="primary" :disabled="loadingState.count > 0" @click="handleBatchConfirm">{{ $t('batch.confirm') }}</el-button>
      <el-button v-if="isAdmin && selectedRows.some(r => r.status === 'pending')" size="small" type="success" :disabled="loadingState.count > 0" @click="handleBatchApprove">{{ $t('batch.approve') }}</el-button>
    </div>

    <ScTable
      :rows="state.rows"
      :loading="state.loading"
      :empty-text="state.error || $t('sc.noRecords')"
      selectable
      @sort-change="handleSortChange"
      @detail="row => $router.push(`/sc/${row.sc_id}`)"
      @selection-change="val => selectedRows = val"
    />

    <el-pagination
      v-if="state.total > state.pageSize"
      :current-page="state.currentPage"
      :page-size="state.pageSize"
      :total="state.total"
      layout="total, sizes, prev, pager, next, jumper"
      @current-change="handlePageChange"
      @size-change="handleSizeChange"
      style="margin-top:12px;justify-content:flex-end"
    />

    <ScFormDialog
      v-model:visible="scDialogVisible"
      :mode="scDialogMode"
      :record="scDialogRecord"
      :users="activeUsers"
      :vendors="vendors"
      @save-draft="handleSaveDraft"
      @save-submit="handleSaveSubmit"
    />

    <BatchProgressModal
      :visible="batchState.active"
      :title="batchTitle"
      :state="batchState"
      @abort="abort"
    />

    <el-dialog v-model="importVisible" title="Import SC" width="500px">
      <el-upload
        :auto-upload="false"
        :on-change="handleFileSelect"
        :limit="1"
        accept=".xlsx,.xls"
        drag
      >
        <el-icon :size="40"><UploadFilled /></el-icon>
        <div>Drop file here or click to upload</div>
        <template #tip>
          <div>Only .xlsx/.xls files</div>
        </template>
      </el-upload>
      <div v-if="importResult" style="margin-top:12px">
        <el-alert v-if="importResult.ok" type="success" :title="`Imported ${importResult.count} records`" closable @close="importResult = null" />
        <el-alert v-else type="error" closable @close="importResult = null">
          <div v-for="e in importResult.errors" :key="e.row">Row {{ e.row }}: {{ e.field }} - {{ e.message }}</div>
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="importVisible = false">Cancel</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Plus, Download, Upload, UploadFilled } from '@element-plus/icons-vue'
import * as XLSX from 'xlsx'
import { useSc } from '@/composables/useSc.js'
import { useVendor } from '@/composables/useVendor.js'
import { useExport } from '@/composables/useExport.js'
import { callApi, loadingState } from '@/api/bridge.js'
import AdvancedFilterBar from '@/components/common/AdvancedFilterBar.vue'
import ScTable from '@/components/sc/ScTable.vue'
import ScFormDialog from '@/components/sc/ScFormDialog.vue'
import { useBatchAction } from '@/composables/useBatchAction.js'
import BatchProgressModal from '@/components/common/BatchProgressModal.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const { state, searchScs, createDraft, submitSc, setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange } = useSc()
const { state: vendorState, searchVendors } = useVendor()
const { exportAll } = useExport()
const { t } = useI18n()
const isAdmin = computed(() => window.__currentUser?.role === 'admin')
const exporting = ref(false)

const scStatuses = [
  { label: t('status.pending'), value: 'pending' }, { label: t('status.approved'), value: 'approved' },
  { label: t('status.denied'), value: 'denied' }, { label: t('status.finished'), value: 'finished' }
]
const requestTypes = ['material', 'service', 'fixed_asset', 'FC']
const activeUsers = ref([])
const vendors = computed(() => vendorState.rows)

// Batch operations
const selectedRows = ref([])
const { state: batchState, runBatch, abort } = useBatchAction()
const batchTitle = ref('')

function showBatchResult(summary, actionName) {
  if (!summary) return
  let msg = `<p><strong>${t('batch.result', { action: t(`batch.${actionName}`) })}</strong></p>`
  msg += `<p style="color:#67c23a">${t('batch.success', { count: summary.succeeded })}</p>`
  msg += `<p style="color:#f56c6c">${t('batch.failed', { count: summary.failed })}</p>`
  if (summary.skipped) {
    msg += `<p style="color:#e6a23c">${t('batch.skipped', { count: summary.skipped })}</p>`
  }
  if (summary.failedItems.length) {
    msg += `<p><strong>${t('batch.failDetail')}:</strong></p><ul>`
    summary.failedItems.forEach(f => {
      msg += `<li>${f.id}: ${f.reason}</li>`
    })
    msg += '</ul>'
  }
  ElMessageBox.alert(msg, t('common.confirm'), {
    dangerouslyUseHTMLString: true,
    confirmButtonText: t('common.confirm')
  })
}

async function handleBatchSubmit() {
  batchTitle.value = t('batch.titleSubmit')
  const summary = await runBatch(selectedRows.value, 'submit', async (row) => {
    await callApi('submit_sc', { sc_id: row.sc_id, data: {} })
  }, t)
  if (summary) await searchScs()
  showBatchResult(summary, 'submit')
}

async function handleBatchConfirm() {
  batchTitle.value = t('batch.titleConfirm')
  const summary = await runBatch(selectedRows.value, 'confirm', async (row) => {
    await callApi('confirm_sc', { sc_id: row.sc_id })
  }, t)
  if (summary) await searchScs()
  showBatchResult(summary, 'confirm')
}

async function handleBatchApprove() {
  batchTitle.value = t('batch.titleApprove')
  const summary = await runBatch(selectedRows.value, 'approve', async (row) => {
    await callApi('approve_sc', { sc_id: row.sc_id, cascade_pos: false })
  }, t)
  if (summary) await searchScs()
  showBatchResult(summary, 'approve')
}

const deadlineOptions = [
  { label: t('filter.unlimited'), value: '' },
  { label: t('filter.within3Years'), value: '3y' },
  { label: t('filter.within2Years'), value: '2y' },
  { label: t('filter.within1Year'), value: '1y' },
  { label: t('filter.within6Months'), value: '6m' },
  { label: t('filter.within5Months'), value: '5m' },
  { label: t('filter.within4Months'), value: '4m' },
  { label: t('filter.within3Months'), value: '3m' },
  { label: t('filter.within2Months'), value: '2m' },
  { label: t('filter.within1Month'), value: '1m' },
]

function computeDeadlineEnd(value) {
  const today = new Date()
  const match = value.match(/^(\d+)([ym])$/)
  if (!match) return null
  const num = parseInt(match[1])
  const unit = match[2]
  if (unit === 'y') today.setFullYear(today.getFullYear() + num)
  else today.setMonth(today.getMonth() + num)
  return today.toISOString().slice(0, 10)
}

const scFilterConfig = [
  { name: 'status', label: t('filter.status'), type: 'select', options: scStatuses },
  { name: 'request_type', label: t('filter.requestType'), type: 'select', options: requestTypes.map(t => ({ label: t, value: t })) },
  { name: 'asset', label: t('filter.asset'), type: 'select', options: [{label:'Y',value:'Y'},{label:'N',value:'N'}] },
  { name: 'cost_center', label: t('filter.costCenter'), type: 'input' },
  { name: 'sc_id', label: t('filter.scId'), type: 'input' },
  { name: 'sc_no', label: t('filter.scNo'), type: 'input' },
  { name: 'requester_id', label: t('filter.requesterId'), type: 'input' },
  { name: 'requester_name', label: t('filter.requesterName'), type: 'input' },
  { name: 'created_by', label: t('filter.createdById'), type: 'input' },
  { name: 'created_by_name', label: t('filter.createdByName'), type: 'input' },
  { name: 'service_period_start', label: t('filter.serviceStart'), type: 'date-range' },
  { name: 'sc_amount', label: t('filter.scAmount'), type: 'amount-range' },
  { name: 'pending_date', label: t('filter.pendingDate'), type: 'date-range' },
  { name: 'approved_date', label: t('filter.approvedDate'), type: 'date-range' },
  { name: 'deadline', label: t('filter.deadline'), type: 'select', options: deadlineOptions },
]

const scDialogVisible = ref(false)
const scDialogMode = ref('create')
const scDialogRecord = ref(null)

function handleFilter({ text, filters }) {
  const transformed = { ...filters }
  if (transformed.deadline) {
    const endDate = computeDeadlineEnd(transformed.deadline)
    if (endDate) {
      transformed.deadline_from = new Date().toISOString().slice(0, 10)
      transformed.deadline_to = endDate
    }
  }
  delete transformed.deadline
  searchScs(text, transformed)
}

function handleReset() {
  resetFilters()
  searchScs()
}

function handleSortChange({ prop, order }) {
  onSortChange({ prop, order })
  searchScs()
}

function handlePageChange(page) { onPageChange(page); searchScs() }
function handleSizeChange(size) { onPageSizeChange(size); searchScs() }

async function handleSaveDraft(data) {
  try {
    const { _attachments, ...formData } = data
    const created = await createDraft(formData)
    if (_attachments?.length) {
      await callApi('add_attachments', { entity_type: 'sc', entity_id: created.sc_id, file_paths: _attachments })
    }
    ElMessage.success(t('sc.draftSaved'))
    scDialogVisible.value = false
    await searchScs()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}

async function handleSaveSubmit(data) {
  try {
    const { _attachments, ...formData } = data
    const created = await createDraft(formData)
    if (_attachments?.length) {
      await callApi('add_attachments', { entity_type: 'sc', entity_id: created.sc_id, file_paths: _attachments })
    }
    await submitSc(created.sc_id, formData)
    ElMessage.success(t('common.saved'))
    scDialogVisible.value = false
    await searchScs()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}

async function handleExport() {
  exporting.value = true
  try {
    const columns = [
      { key: 'status', label: t('exportCol.status') },
      { key: 'sc_no', label: t('exportCol.scNo') },
      { key: 'requester_name', label: t('exportCol.requester') },
      { key: 'request_type', label: t('exportCol.type') },
      { key: 'asset', label: t('exportCol.asset') },
      { key: 'cost_center', label: t('exportCol.costCenter') },
      { key: 'sc_amount', label: t('exportCol.scAmount') },
      { key: 'pending_date', label: t('exportCol.pendingDate'), getValue: r => (r.pending_date || '').slice(0, 10) },
      { key: 'approved_date', label: t('exportCol.approvedDate'), getValue: r => (r.approved_date || '').slice(0, 10) },
      { key: 'created_at', label: t('exportCol.created'), getValue: r => (r.created_at || '').replace('T', ' ').slice(0, 19) },
      { key: 'submitted_date', label: t('sc.submittedDate'), getValue: r => (r.submitted_date || '').slice(0, 10) },
      { key: 'description', label: t('exportCol.description') }
    ]
    await exportAll('search_scs', {
      filters: state.filters,
      sort: state.sort,
      direction: state.direction
    }, columns, `SC_List_${new Date().toISOString().slice(0, 10)}`)
    ElMessage.success(t('export.exported'))
  } catch (e) {
    ElMessage.error(e.message || t('export.failed'))
  } finally {
    exporting.value = false
  }
}

// SC import
const importVisible = ref(false)
const importResult = ref(null)

async function handleFileSelect(uploadFile) {
  importResult.value = null
  const file = uploadFile.raw
  try {
    const data = await file.arrayBuffer()
    const wb = XLSX.read(data, { type: 'array' })
    const ws = wb.Sheets[wb.SheetNames[0]]
    const rows = XLSX.utils.sheet_to_json(ws, { defval: '' })
    importResult.value = await callApi('import_scs', { rows })
    if (importResult.value.ok) {
      importVisible.value = false
      searchScs()
    }
  } catch (e) {
    importResult.value = { ok: false, errors: [{ row: '-', field: '', message: e.message }] }
  }
}

async function downloadTemplate() {
  try {
    const result = await callApi('download_sc_template')
    const saveResult = await callApi('save_file', { filename: result.filename, data: result.data })
    if (saveResult?.cancelled) return
    ElMessage.success('Template downloaded')
  } catch (e) {
    ElMessage.error(e.message || 'Failed to download template')
  }
}

onMounted(async () => {
  try {
    activeUsers.value = await callApi('list_users')
  } catch { /* ignore — user list is non-critical */ }
  const filters = {}
  if (route.query.status) {
    filters.status = route.query.status
    setFilters(filters)
  }
  await Promise.all([searchScs(null, Object.keys(filters).length ? filters : null), searchVendors()])
})
</script>
