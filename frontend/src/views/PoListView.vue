<template>
  <div>
    <AdvancedFilterBar
      :filter-config="poFilterConfig"
      @filter="handleFilter"
      @reset="handleReset"
    />

    <div style="margin-bottom:12px;display:flex;gap:8px">
      <el-button type="primary" @click="openCreatePoDialog">
        <el-icon><Plus /></el-icon> {{ $t('po.addPo') }}
      </el-button>
      <el-button @click="handleExport" :loading="exporting">
        <el-icon><Download /></el-icon> {{ $t('common.export') }}
      </el-button>
    </div>

    <PoTable
      :rows="state.rows"
      :loading="state.loading"
      @row-click="row => $router.push(`/sc/${row.sc_id}/po/${row.po_id}`)"
      @edit="row => { poDialogRecord = row; poDialogMode = 'edit'; poDialogVisible = true }"
      @submit="row => handleSubmitPo(row)"
      @finish="row => handleFinishPo(row)"
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
      :vendors="vendors"
      :sc-record="selectedScRecord"
      @save="handlePoSave"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Plus, Download } from '@element-plus/icons-vue'
import { callApi } from '@/api/bridge.js'
import { usePo } from '@/composables/usePo.js'
import { useVendor } from '@/composables/useVendor.js'
import { useExport } from '@/composables/useExport.js'
import AdvancedFilterBar from '@/components/common/AdvancedFilterBar.vue'
import PoTable from '@/components/po/PoTable.vue'
import PoFormDialog from '@/components/po/PoFormDialog.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const { t } = useI18n()

const { state, searchPos, createPo, updatePo, submitPo, finishPo, setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange } = usePo()
const { state: vendorState, searchVendors } = useVendor()
const { exportAll } = useExport()
const exporting = ref(false)

const vendors = computed(() => vendorState.rows)

const poStatuses = [
  { label: t('status.draft'), value: 'draft' },
  { label: t('status.activing'), value: 'activing' },
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
  { name: 'contract_type', label: t('filter.contractType'), type: 'select', options: [{label:'PO',value:'PO'},{label:'Contract',value:'Contract'}] },
  { name: 'cost_center', label: t('filter.costCenter'), type: 'input' },
  { name: 'purchaser', label: t('filter.purchaser'), type: 'input' },
  { name: 'po_amount', label: t('filter.poAmount'), type: 'amount-range' },
  { name: 'contract_from', label: t('filter.contractFrom'), type: 'date-range' },
  { name: 'contract_to', label: t('filter.contractTo'), type: 'date-range' },
  { name: 'activing_date', label: t('filter.activingDate'), type: 'date-range' },
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

function confirmScSelection() {
  if (!selectedScId.value) return
  selectedScRecord.value = eligibleScs.value.find(s => s.sc_id === selectedScId.value) || null
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
    let poId, scId
    if (poDialogMode.value === 'create') {
      const payload = { ...formData, sc_id: selectedScRecord.value?.sc_id || formData.sc_id }
      const created = await createPo(payload)
      poId = created.po_id
      scId = created.sc_id || payload.sc_id
    } else {
      poId = poDialogRecord.value?.po_id
      scId = poDialogRecord.value?.sc_id
      await updatePo(poId, formData)
    }
    if (_attachments?.length) {
      await callApi('add_attachments', { entity_type: 'po', entity_id: poId, file_paths: _attachments, parent_sc_id: scId })
    }
    ElMessage.success(t('common.saved'))
    poDialogVisible.value = false
    await searchPos()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}

function handlePageChange(page) { onPageChange(page); searchPos() }
function handleSizeChange(size) { onPageSizeChange(size); searchPos() }

async function handleExport() {
  exporting.value = true
  try {
    const columns = [
      { key: 'status', label: t('export.status') },
      { key: 'po_no', label: t('export.poNo') },
      { key: 'sc_no', label: t('export.scNo') },
      { key: 'vendor_name', label: t('export.vendor') },
      { key: 'contract_type', label: t('exportCol.contractType') },
      { key: 'cost_center', label: t('exportCol.costCenter') },
      { key: 'po_amount', label: t('export.poAmount') },
      { key: 'open_po_amount', label: t('export.openPoAmount') },
      { key: 'contract_from', label: t('export.contractFrom'), getValue: r => (r.contract_from || '').slice(0, 10) },
      { key: 'contract_to', label: t('export.contractTo'), getValue: r => (r.contract_to || '').slice(0, 10) },
      { key: 'activing_date', label: t('exportCol.activingDate'), getValue: r => (r.activing_date || '').slice(0, 10) }
    ]
    await exportAll('search_pos', {
      filters: state.filters,
      sort: state.sort,
      direction: state.direction
    }, columns, `PO_List_${new Date().toISOString().slice(0, 10)}`)
    ElMessage.success(t('msg.exportedSuccessfully'))
  } catch (e) {
    ElMessage.error(e.message || t('msg.exportFailed'))
  } finally {
    exporting.value = false
  }
}

onMounted(async () => {
  await Promise.all([searchPos(), searchVendors(), loadEligibleScs()])
})
</script>
