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
      <el-button @click="handleExport" :loading="exporting">
        <el-icon><Download /></el-icon> {{ $t('common.export') }}
      </el-button>
    </div>

    <el-table :data="state.rows" v-loading="state.loading" stripe border @row-click="handleRowClick">
      <el-table-column :label="$t('common.status')" width="100">
        <template #default="{ row }"><StatusBadge :status="row.status" /></template>
      </el-table-column>
      <el-table-column prop="gr_id" :label="$t('gr.grId')" width="120" />
      <el-table-column prop="po_no" :label="$t('gr.poNo')" width="130" />
      <el-table-column prop="sc_no" :label="$t('gr.scNo')" width="130" />
      <el-table-column prop="vendor_name" :label="$t('gr.vendor')" min-width="150" show-overflow-tooltip />
      <el-table-column prop="estimated_amount" :label="$t('gr.estimated')" width="120">
        <template #default="{ row }"><AmountDisplay :value="row.estimated_amount" /></template>
      </el-table-column>
      <el-table-column prop="con_value" :label="$t('gr.conValue')" width="120">
        <template #default="{ row }"><AmountDisplay :value="row.con_value" /></template>
      </el-table-column>
      <el-table-column prop="pending_date" :label="$t('gr.pendingDate')" width="110">
        <template #default="{ row }">{{ (row.pending_date || '').slice(0, 10) || '-' }}</template>
      </el-table-column>
      <el-table-column prop="approved_date" :label="$t('gr.approvedDate')" width="110">
        <template #default="{ row }">{{ (row.approved_date || '').slice(0, 10) || '-' }}</template>
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
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Download } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import { callApi } from '@/api/bridge.js'
import { useGr } from '@/composables/useGr.js'
import { useExport } from '@/composables/useExport.js'
import AdvancedFilterBar from '@/components/common/AdvancedFilterBar.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'
import GrFormDialog from '@/components/po/GrFormDialog.vue'
import { ElMessage } from 'element-plus'

const router = useRouter()
const { t } = useI18n()
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
  { name: 'po_id', label: t('gr.poId'), type: 'input' },
  { name: 'sc_id', label: t('gr.scId'), type: 'input' },
  { name: 'requester_id', label: t('gr.requester'), type: 'input' },
  { name: 'vendor_id', label: t('gr.vendorId'), type: 'input' },
  { name: 'estimated_amount', label: t('gr.estAmount'), type: 'amount-range' },
  { name: 'con_value', label: t('gr.conValue'), type: 'amount-range' },
  { name: 'pending_date', label: t('filter.pendingDate'), type: 'date-range' },
  { name: 'approved_date', label: t('filter.approvedDate'), type: 'date-range' },
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

function handleRowClick(row) {
  if (row.sc_id && row.po_id) {
    router.push(`/sc/${row.sc_id}/po/${row.po_id}/gr/${row.gr_id}`)
  }
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
    const payload = { ...formData, po_id: grSelectedPoId.value }
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
      { key: 'con_value', label: t('gr.conValue') },
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

onMounted(async () => {
  try { activeUsers.value = await callApi('list_users') } catch {}
  await Promise.all([searchGrs(), loadEligibleScs()])
})
</script>
