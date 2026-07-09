<template>
  <div>
    <AdvancedFilterBar
      :filter-config="poFilterConfig"
      @filter="handleFilter"
      @reset="handleReset"
    />

    <div style="margin-bottom:12px;display:flex;gap:8px">
      <el-dropdown @command="handleCreatePoCommand" style="margin-right:8px">
        <el-button type="primary">
          <el-icon><Plus /></el-icon> {{ $t('po.addPo') }} <el-icon><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="regular">{{ $t('po.newRegularPo') }}</el-dropdown-item>
            <el-dropdown-item command="fc">{{ $t('po.newFcPo') }}</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button @click="importVisible = true">
        <el-icon><Upload /></el-icon> Import
      </el-button>
      <el-button @click="downloadTemplate">
        <el-icon><Download /></el-icon> Template
      </el-button>
      <el-button @click="handleExport" :loading="exporting">
        <el-icon><Download /></el-icon> {{ $t('common.export') }}
      </el-button>
      <el-button v-if="isAdmin" @click="openAnnualReportDialog">
        <el-icon><Download /></el-icon> {{ $t('po.annualReport') }}
      </el-button>
    </div>

    <PoTable
      :rows="state.rows"
      :loading="state.loading"
      selectable
      @selection-change="val => selectedRows = val"
      @detail="row => row.sc_id
        ? $router.push(`/sc/${row.sc_id}/po/${row.po_id}`)
        : $router.push(`/po/${row.po_id}`)"
      @edit="row => { poDialogRecord = row; poDialogMode = 'edit'; poDialogVisible = true }"
      @submit="row => handleSubmitPo(row)"
      @finish="row => handleFinishPo(row)"
    />

    <el-pagination
      :current-page="state.currentPage"
      :page-size="state.pageSize"
      :total="state.total"
      layout="total, sizes, prev, pager, next, jumper"
      @current-change="handlePageChange"
      @size-change="handleSizeChange"
      style="margin-top:12px;justify-content:flex-end"
    />

    <!-- SC selection dialog for creating PO -->
    <el-dialog
      v-model="scSelectVisible"
      :title="$t('po.addPo')"
      width="420px"
    >
      <el-form label-position="top">
        <el-form-item :label="$t('po.selectSc')">
          <el-select v-model="selectedScId" filterable placeholder="Search SC..." style="width:100%">
            <el-option
              v-for="sc in eligibleScs"
              :key="sc.sc_id"
              :label="`${sc.sc_no || sc.sc_id} — ${sc.description || ''}`"
              :value="sc.sc_id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="scSelectVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :disabled="!selectedScId" @click="confirmScSelection">
          {{ $t('common.confirm') }}
        </el-button>
      </template>
    </el-dialog>

    <PoFormDialog
      v-model:visible="poDialogVisible"
      :mode="poDialogMode"
      :record="poDialogRecord"
      :vendors="scLinkedVendors"
      :sc-record="selectedScRecord"
      @save="handlePoSave"
      @save-draft="handlePoSaveDraft"
    />

    <ImportPreviewDialog
      v-model:visible="importVisible"
      entity-type="PO"
      :columns="poImportColumns"
      :rules-text="$t('po.importRules')"
      @imported="searchPos"
    />

    <ExportDialog
      v-model:visible="exportDialogVisible"
      entity-type="po"
      :filters="state.filters"
      :sort="state.sort"
      :direction="state.direction"
      :selected-ids="selectedRows.map(r => r.po_id)"
      :filtered-count="state.total"
      :total-count="state.total"
    />
    <el-dialog
      v-model="annualReportVisible"
      :title="$t('po.annualReportTitle')"
      width="360px"
    >
      <el-form label-position="top">
        <el-form-item :label="$t('po.selectYear')">
          <el-date-picker
            v-model="annualReportYear"
            type="year"
            placeholder="YYYY"
            format="YYYY"
            value-format="YYYY"
            :clearable="false"
            style="width:100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="annualReportVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="annualExporting" @click="handleAnnualExport">
          {{ $t('common.export') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Plus, ArrowDown, Download, Upload } from '@element-plus/icons-vue'
import { callApi } from '@/api/bridge.js'
import { usePo } from '@/composables/usePo.js'
import { useExport } from '@/composables/useExport.js'
import AdvancedFilterBar from '@/components/common/AdvancedFilterBar.vue'
import PoTable from '@/components/po/PoTable.vue'
import PoFormDialog from '@/components/po/PoFormDialog.vue'
import ImportPreviewDialog from '@/components/common/ImportPreviewDialog.vue'
import ExportDialog from '@/components/export/ExportDialog.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const { t } = useI18n()
const isAdmin = computed(() => window.__currentUser?.role === 'admin')

const { state, searchPos, createPo, updatePo, submitPo, finishPo, setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange } = usePo()
const { exportRows } = useExport()
const exporting = ref(false)
const selectedRows = ref([])
const exportDialogVisible = ref(false)
const annualReportVisible = ref(false)
const annualReportYear = ref(new Date().getFullYear().toString())
const annualExporting = ref(false)

const scLinkedVendors = ref([])

const poStatuses = [
  { label: t('status.draft'), value: 'draft' },
  { label: t('status.active'), value: 'active' },
  { label: t('status.finished'), value: 'finished' }
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

const poFilterConfig = [
  { name: 'status', label: t('filter.status'), type: 'select', options: poStatuses },
  { name: 'po_id', label: t('filter.poId'), type: 'input' },
  { name: 'po_no', label: t('filter.poNo'), type: 'input' },
  { name: 'sc_id', label: t('filter.scId'), type: 'input' },
  { name: 'vendor_id', label: t('filter.vendorId'), type: 'input' },
  { name: 'vendor_name', label: t('filter.vendorName'), type: 'input' },
  { name: 'is_fc_po', label: t('filter.isFcPo'), type: 'select', options: [{ label: 'FC PO', value: '1' }, { label: 'Regular PO', value: '0' }] },
  { name: 'contract_type', label: t('filter.contractType'), type: 'select', options: [{label:'PO',value:'PO'},{label:'Contract',value:'Contract'}] },
  { name: 'cost_center', label: t('filter.costCenter'), type: 'input' },
  { name: 'purchaser', label: t('filter.purchaser'), type: 'input' },
  { name: 'po_amount', label: t('filter.poAmount'), type: 'amount-range' },
  { name: 'contract_from', label: t('filter.contractFrom'), type: 'date-range' },
  { name: 'contract_to', label: t('filter.contractTo'), type: 'date-range' },
  { name: 'active_date', label: t('filter.activeDate'), type: 'date-range' },
  { name: 'deadline', label: t('filter.deadline'), type: 'select', options: deadlineOptions },
]

const poDialogVisible = ref(false)
const poDialogMode = ref('create')
const poDialogRecord = ref(null)

// SC selection for creating PO
const scSelectVisible = ref(false)
const selectedScId = ref('')
const selectedScRecord = ref(null)
const eligibleScs = ref([])

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

function openCreatePoDialog() {
  selectedScId.value = ''
  selectedScRecord.value = null
  scSelectVisible.value = true
}

function handleCreatePoCommand(command) {
  if (command === 'regular') {
    openCreatePoDialog()
  } else if (command === 'fc') {
    openCreateFcPoDialog()
  }
}

async function openCreateFcPoDialog() {
  selectedScId.value = ''
  selectedScRecord.value = null
  scSelectVisible.value = false
  try {
    const result = await callApi('search_vendors', { limit: 500 })
    scLinkedVendors.value = result.rows || []
  } catch { scLinkedVendors.value = [] }
  poDialogMode.value = 'create'
  poDialogRecord.value = null
  poDialogVisible.value = true
}

async function confirmScSelection() {
  if (!selectedScId.value) return
  selectedScRecord.value = eligibleScs.value.find(s => s.sc_id === selectedScId.value) || null
  try {
    const detail = await callApi('get_sc_detail', { sc_id: selectedScId.value })
    scLinkedVendors.value = detail?.vendors || []
  } catch { scLinkedVendors.value = [] }
  scSelectVisible.value = false
  poDialogMode.value = 'create'
  poDialogRecord.value = null
  poDialogVisible.value = true
}

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
  searchPos(text, transformed)
}

function handleReset() {
  resetFilters()
  searchPos()
}

async function handleSubmitPo(row) {
  try {
    await ElMessageBox.confirm(t('common.submit') + ' this PO?', t('common.confirm'), { type: 'warning' })
    await submitPo(row.po_id)
    ElMessage.success(t('common.submit') + ' ' + t('msg.saved'))
    await searchPos()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleFinishPo(row) {
  try {
    await ElMessageBox.confirm(t('confirm.finishPo'), t('common.confirm'), { type: 'warning' })
    await finishPo(row.po_id)
    ElMessage.success(t('msg.poFinished'))
    await searchPos()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handlePoSave(data) {
  try {
    const { _attachments, ...formData } = data
    const isFcPo = !selectedScRecord.value
    let poId, scId
    if (poDialogMode.value === 'create') {
      const payload = { ...formData }
      if (isFcPo) {
        payload.request_type = 'FC'
      } else {
        payload.sc_id = selectedScRecord.value?.sc_id || formData.sc_id
      }
      const created = await createPo(payload)
      poId = created.po_id
      scId = created.sc_id || payload.sc_id
    } else {
      poId = poDialogRecord.value?.po_id
      scId = poDialogRecord.value?.sc_id
      await updatePo(poId, formData)
    }
    if (_attachments?.length) {
      await callApi('add_attachments', {
        entity_type: 'po', entity_id: poId,
        file_paths: _attachments, parent_sc_id: scId || null
      })
    }
    ElMessage.success(t('common.saved'))
    poDialogVisible.value = false
    await searchPos()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}

async function handlePoSaveDraft(data) {
  try {
    const { _attachments, ...formData } = data
    const isFcPo = !selectedScRecord.value
    const payload = { ...formData, status: 'draft' }
    if (isFcPo) {
      payload.request_type = 'FC'
    } else {
      payload.sc_id = selectedScRecord.value?.sc_id || formData.sc_id
    }
    const created = await createPo(payload)
    if (_attachments?.length) {
      await callApi('add_attachments', {
        entity_type: 'po', entity_id: created.po_id,
        file_paths: _attachments, parent_sc_id: created.sc_id || null
      })
    }
    ElMessage.success(t('po.draftSaved'))
    poDialogVisible.value = false
    await searchPos()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}

function handlePageChange(page) { onPageChange(page); searchPos() }
function handleSizeChange(size) { onPageSizeChange(size); searchPos() }

function handleExport() {
  exportDialogVisible.value = true
}

function openAnnualReportDialog() {
  annualReportYear.value = new Date().getFullYear().toString()
  annualReportVisible.value = true
}

async function handleAnnualExport() {
  annualExporting.value = true
  try {
    const year = annualReportYear.value || new Date().getFullYear().toString()
    const previousYear = String(Number(year) - 1)
    const result = await callApi('get_po_annual_report', { year })
    const rows = result.rows || []
    const columns = [
      { key: 'requester', label: 'Requester' },
      { key: 'sc_no', label: 'SC no' },
      { key: 'po_no', label: 'PO number' },
      { key: 'short_text', label: 'Short Text' },
      { key: 'sc_amount', label: 'SC amount' },
      { key: 'po_amount', label: 'PO amount' },
      { key: 'previous_year_gr', label: `${previousYear} GR` },
      { key: 'previous_year_provision', label: `${previousYear} Provision` },
      { key: 'selected_year_gr', label: `${year} GR` },
      { key: 'selected_year_to_be_gr', label: `${year} to be GR` },
      { key: 'selected_year_fc_gr', label: `${year} FC GR` },
      { key: 'remark', label: 'Remark' },
    ]
    const saveResult = await exportRows(rows, columns, `PO_Annual_Report_${year}`)
    if (saveResult?.cancelled) return
    ElMessage.success(t('msg.exportedSuccessfully'))
    annualReportVisible.value = false
  } catch (e) {
    ElMessage.error(e.message || t('msg.exportFailed'))
  } finally {
    annualExporting.value = false
  }
}

// PO import
const importVisible = ref(false)

const poImportColumns = [
  { prop: 'sc_no', label: t('sc.scNo'), width: '120' },
  { prop: 'vendor_id', label: t('po.vendor'), width: '100' },
  { prop: 'po_no', label: t('po.poNo'), width: '120' },
  { prop: 'requester_id', label: t('sc.requester'), width: '100' },
  { prop: 'po_amount', label: t('po.poAmount'), width: '100' },
  { prop: 'status', label: t('common.status'), width: '90' },
  { prop: 'contract_from', label: t('po.contractFrom'), width: '110' },
  { prop: 'contract_to', label: t('po.contractTo'), width: '110' },
  { prop: 'contract_no', label: t('po.contractNo'), width: '120' },
  { prop: 'payment_frequency', label: t('po.paymentFrequency'), width: '100' },
  { prop: 'contract_pos', label: t('po.contractPos'), width: '90' },
  { prop: 'contract_type', label: t('po.contractType'), width: '100' },
  { prop: 'cost_center', label: t('po.costCenter'), width: '100' },
  { prop: 'purchaser', label: t('po.purchaser'), width: '100' },
  { prop: 'active_date', label: t('po.activeDate'), width: '110' },
]

async function downloadTemplate() {
  try {
    const result = await callApi('download_po_template')
    const saveResult = await callApi('save_file', { filename: result.filename, data: result.data })
    if (saveResult?.cancelled) return
    ElMessage.success('Template downloaded')
  } catch (e) {
    ElMessage.error(e.message || 'Failed to download template')
  }
}

onMounted(async () => {
  const filters = {}
  if (route.query.status) {
    filters.status = route.query.status
    setFilters(filters)
  }
  await Promise.all([searchPos(null, Object.keys(filters).length ? filters : null), loadEligibleScs()])
})
</script>
