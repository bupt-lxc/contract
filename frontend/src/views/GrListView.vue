<template>
  <div>
    <AdvancedFilterBar
      :filter-config="grFilterConfig"
      @filter="handleFilter"
      @reset="handleReset"
    />

    <div style="margin-bottom:12px;display:flex;gap:8px">
      <el-button type="primary" @click="openCreateGrDialog">
        <el-icon><Plus /></el-icon> {{ $t('gr.addGr') }}
      </el-button>
      <el-button @click="importVisible = true">
        <el-icon><Upload /></el-icon> Import
      </el-button>
      <el-button @click="downloadTemplate">
        <el-icon><Download /></el-icon> Template
      </el-button>
      <el-button @click="handleExport" :loading="exporting">
        <el-icon><Download /></el-icon> {{ $t('common.export') }}
      </el-button>
    </div>

    <div v-if="selectedRows.length" style="margin-bottom:12px;display:flex;align-items:center;gap:12px;padding:8px 12px;background:#f0f9ff;border-radius:4px">
      <span style="font-size:13px;color:#1d4ed8;font-weight:500">{{ $t('batch.selected', { count: selectedRows.length }) }}</span>
      <el-button v-if="selectedRows.some(r => r.status === 'draft')" size="small" type="primary" @click="handleBatchSubmit">{{ $t('batch.submit') }}</el-button>
      <el-button v-if="isAdmin && selectedRows.some(r => r.status === 'manager_confirm')" size="small" type="primary" @click="handleBatchConfirm">{{ $t('batch.confirm') }}</el-button>
    </div>

    <el-table :data="state.rows" v-loading="state.loading" stripe border @selection-change="val => selectedRows = val" @sort-change="onSortChange" :default-sort="{ prop: 'created_at', order: 'descending' }">
      <el-table-column type="selection" width="50" />
      <el-table-column :label="$t('common.status')" width="100" prop="status" sortable>
        <template #default="{ row }"><StatusBadge :status="row.status" /></template>
      </el-table-column>
      <el-table-column prop="gr_id" :label="$t('gr.grId')" width="120" sortable />
      <el-table-column prop="gr_no" :label="$t('gr.grNo')" width="120" sortable>
        <template #default="{ row }">{{ row.gr_no || '-' }}</template>
      </el-table-column>
      <el-table-column prop="po_no" :label="$t('gr.poNo')" width="130" sortable />
      <el-table-column prop="sc_no" :label="$t('gr.scNo')" width="130" sortable />
      <el-table-column prop="vendor_name" :label="$t('gr.vendor')" min-width="150" show-overflow-tooltip sortable />
      <el-table-column prop="estimated_amount" :label="$t('gr.estimated')" width="120" sortable>
        <template #default="{ row }"><AmountDisplay :value="row.estimated_amount" /></template>
      </el-table-column>
      <el-table-column prop="tax_rate" :label="$t('gr.taxRate')" width="80" align="center" sortable>
        <template #default="{ row }">{{ row.tax_rate != null ? row.tax_rate + '%' : '-' }}</template>
      </el-table-column>
      <el-table-column prop="con_value" :label="$t('gr.conValue')" width="120" sortable>
        <template #default="{ row }"><AmountDisplay :value="row.con_value" /></template>
      </el-table-column>
      <el-table-column prop="pending_date" :label="$t('gr.pendingDate')" width="110" sortable>
        <template #default="{ row }">{{ (row.pending_date || '').slice(0, 10) || '-' }}</template>
      </el-table-column>
      <el-table-column prop="approved_date" :label="$t('gr.approvedDate')" width="110" sortable>
        <template #default="{ row }">{{ (row.approved_date || '').slice(0, 10) || '-' }}</template>
      </el-table-column>
      <el-table-column :label="$t('common.actions')" width="70" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click.stop="goToDetail(row)">{{ $t('common.detail') }}</el-button>
        </template>
      </el-table-column>
      <template #empty><el-empty :description="$t('gr.noRecords')" /></template>
    </el-table>

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

    <!-- SC+PO selection dialog for creating GR -->
    <el-dialog
      v-model="grSelectVisible"
      :title="$t('gr.addGr')"
      width="420px"
    >
      <el-form label-position="top">
        <el-form-item :label="$t('gr.selectSc')">
          <el-select v-model="grSelectedScId" filterable placeholder="Search SC..." style="width:100%" @change="onGrScChange">
            <el-option
              v-for="sc in eligibleScs"
              :key="sc.sc_id"
              :label="`${sc.sc_no || sc.sc_id} — ${sc.description || ''}`"
              :value="sc.sc_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('gr.selectPo')">
          <el-select v-model="grSelectedPoId" filterable placeholder="Search PO..." style="width:100%" :disabled="!grSelectedScId">
            <el-option
              v-for="po in eligiblePos"
              :key="po.po_id"
              :label="`${po.po_no || po.po_id} — ${po.vendor_name || ''}`"
              :value="po.po_id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="grSelectVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :disabled="!grSelectedPoId" @click="confirmGrSelection">
          {{ $t('common.confirm') }}
        </el-button>
      </template>
    </el-dialog>

    <GrFormDialog
      v-model:visible="grDialogVisible"
      :mode="grDialogMode"
      :record="grDialogRecord"
      :users="activeUsers"
      @save="handleGrSave"
    />

    <el-dialog v-model="importVisible" title="Import GR" width="500px">
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

    <BatchProgressModal
      :visible="batchState.active"
      :title="batchTitle"
      :state="batchState"
      @abort="abort"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Plus, Download, Upload, UploadFilled } from '@element-plus/icons-vue'
import * as XLSX from 'xlsx'
import { useI18n } from 'vue-i18n'
import { callApi } from '@/api/bridge.js'
import { useGr } from '@/composables/useGr.js'
import { useExport } from '@/composables/useExport.js'
import AdvancedFilterBar from '@/components/common/AdvancedFilterBar.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'
import GrFormDialog from '@/components/po/GrFormDialog.vue'
import { useBatchAction } from '@/composables/useBatchAction.js'
import BatchProgressModal from '@/components/common/BatchProgressModal.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const isAdmin = computed(() => window.__currentUser?.role === 'admin')
const { state, searchGrs, setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange } = useGr()
const { exportAll } = useExport()
const exporting = ref(false)

const grStatuses = [
  { label: t('status.pending'), value: 'pending' }, { label: t('status.approved'), value: 'approved' }, { label: t('status.cancelled'), value: 'cancelled' }
]

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

const grFilterConfig = [
  { name: 'status', label: t('common.status'), type: 'select', options: grStatuses },
  { name: 'gr_id', label: t('gr.grId'), type: 'input' },
  { name: 'gr_no', label: t('gr.grNo'), type: 'input' },
  { name: 'po_id', label: t('gr.poId'), type: 'input' },
  { name: 'sc_id', label: t('gr.scId'), type: 'input' },
  { name: 'requester_id', label: t('gr.requester'), type: 'input' },
  { name: 'vendor_id', label: t('gr.vendorId'), type: 'input' },
  { name: 'estimated_amount', label: t('gr.estAmount'), type: 'amount-range' },
  { name: 'tax_rate', label: t('gr.taxRate'), type: 'input' },
  { name: 'con_value', label: t('gr.conValue'), type: 'amount-range' },
  { name: 'pending_date', label: t('filter.pendingDate'), type: 'date-range' },
  { name: 'approved_date', label: t('filter.approvedDate'), type: 'date-range' },
  { name: 'goods_service_description', label: t('gr.goodsServiceDescription'), type: 'input' },
  { name: 'confirmation_name', label: t('gr.confirmationName'), type: 'input' },
  { name: 'delivery_from', label: t('gr.deliveryFrom'), type: 'date-range' },
  { name: 'delivery_to', label: t('gr.deliveryTo'), type: 'date-range' },
  { name: 'last_delivery', label: t('gr.lastDelivery'), type: 'select', options: [{ label: t('common.yes'), value: 'Y' }, { label: t('common.no'), value: 'N' }] },
  { name: 'deadline', label: t('filter.deadline'), type: 'select', options: deadlineOptions },
]

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
  searchGrs(text, transformed)
}

function handleReset() {
  resetFilters()
  searchGrs()
}

function goToDetail(row) {
  router.push(`/sc/${row.sc_id}/po/${row.po_id}/gr/${row.gr_id}`)
}

function handlePageChange(page) { onPageChange(page); searchGrs() }
function handleSizeChange(size) { onPageSizeChange(size); searchGrs() }

// ── Create GR with SC→PO selection ──
const grSelectVisible = ref(false)
const grSelectedScId = ref('')
const grSelectedPoId = ref('')
const eligibleScs = ref([])
const eligiblePos = ref([])
const activeUsers = ref([])

const grDialogVisible = ref(false)
const grDialogMode = ref('create')
const grDialogRecord = ref(null)

async function loadEligibleScs() {
  try {
    const result = await callApi('search_scs', {
      filters: { status: 'approved' },
      limit: 500, offset: 0,
      sort: 'created_at', direction: 'desc'
    })
    eligibleScs.value = result.rows || result || []
  } catch { eligibleScs.value = [] }
}

async function onGrScChange(scId) {
  grSelectedPoId.value = ''
  eligiblePos.value = []
  if (!scId) return
  try {
    const result = await callApi('search_pos', {
      filters: { sc_id: scId },
      limit: 200, offset: 0,
      sort: 'created_at', direction: 'desc'
    })
    eligiblePos.value = result.rows || result || []
  } catch { eligiblePos.value = [] }
}

function openCreateGrDialog() {
  grSelectedScId.value = ''
  grSelectedPoId.value = ''
  eligiblePos.value = []
  grSelectVisible.value = true
}

function confirmGrSelection() {
  if (!grSelectedPoId.value) return
  grSelectVisible.value = false
  grDialogMode.value = 'create'
  grDialogRecord.value = null
  grDialogVisible.value = true
}

async function handleGrSave(data) {
  try {
    const { _attachments, ...formData } = data
    const payload = { ...formData, po_id: grSelectedPoId.value, status: 'manager_confirm' }
    const result = await callApi('create_gr', { data: payload })
    const created = result
    if (_attachments?.length && created?.gr_id) {
      // Get po info for parent references
      const po = eligiblePos.value.find(p => p.po_id === grSelectedPoId.value)
      await callApi('add_attachments', {
        entity_type: 'gr', entity_id: created.gr_id,
        file_paths: _attachments,
        parent_sc_id: po?.sc_id, parent_po_id: grSelectedPoId.value
      })
    }
    ElMessage.success(t('common.saved'))
    grDialogVisible.value = false
    await searchGrs()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}

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
    await callApi('submit_gr', { gr_id: row.gr_id })
  }, t)
  if (summary) await searchGrs()
  showBatchResult(summary, 'submit')
}

async function handleBatchConfirm() {
  batchTitle.value = t('batch.titleConfirm')
  const summary = await runBatch(selectedRows.value, 'confirm', async (row) => {
    await callApi('confirm_gr', { gr_id: row.gr_id })
  }, t)
  if (summary) await searchGrs()
  showBatchResult(summary, 'confirm')
}

async function handleExport() {
  exporting.value = true
  try {
    const columns = [
      { key: 'status', label: t('common.status') },
      { key: 'gr_id', label: t('gr.grId') },
      { key: 'po_no', label: t('gr.poNo') },
      { key: 'sc_no', label: t('gr.scNo') },
      { key: 'vendor_name', label: t('gr.vendor') },
      { key: 'estimated_amount', label: t('gr.estimated') },
      { key: 'tax_rate', label: t('gr.taxRate') },
      { key: 'con_value', label: t('gr.conValue') },
      { key: 'goods_service_description', label: t('gr.goodsServiceDescription') },
      { key: 'confirmation_name', label: t('gr.confirmationName') },
      { key: 'delivery_from', label: t('gr.deliveryFrom'), getValue: r => (r.delivery_from || '').slice(0, 10) },
      { key: 'delivery_to', label: t('gr.deliveryTo'), getValue: r => (r.delivery_to || '').slice(0, 10) },
      { key: 'last_delivery', label: t('gr.lastDelivery') },
      { key: 'pending_date', label: t('exportCol.pendingDate'), getValue: r => (r.pending_date || '').slice(0, 10) },
      { key: 'approved_date', label: t('exportCol.approvedDate'), getValue: r => (r.approved_date || '').slice(0, 10) }
    ]
    await exportAll('search_grs', {
      filters: state.filters,
      sort: state.sort,
      direction: state.direction
    }, columns, `GR_List_${new Date().toISOString().slice(0, 10)}`)
    ElMessage.success(t('export.success'))
  } catch (e) {
    ElMessage.error(e.message || t('export.failed'))
  } finally {
    exporting.value = false
  }
}

// GR import
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
    importResult.value = await callApi('import_grs', { rows })
    if (importResult.value.ok) {
      importVisible.value = false
      searchGrs()
    }
  } catch (e) {
    importResult.value = { ok: false, errors: [{ row: '-', field: '', message: e.message }] }
  }
}

async function downloadTemplate() {
  const result = await callApi('download_gr_template')
  const binary = atob(result.data)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  const blob = new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = result.filename
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(async () => {
  try { activeUsers.value = await callApi('list_users') } catch {}
  const filters = {}
  if (route.query.status) {
    filters.status = route.query.status
    setFilters(filters)
  }
  await Promise.all([searchGrs(null, Object.keys(filters).length ? filters : null), loadEligibleScs()])
})
</script>
