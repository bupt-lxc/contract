<template>
  <div>
    <AdvancedFilterBar
      :filter-config="poFilterConfig"
      @filter="handleFilter"
      @reset="handleReset"
    />

    <div style="margin-bottom:12px">
      <el-button @click="handleExport" :loading="exporting">
        <el-icon><Download /></el-icon> {{ $t('common.export') }}
      </el-button>
    </div>

    <PoTable
      :rows="state.rows"
      :loading="state.loading"
      @row-click="row => $router.push(`/sc/${row.sc_id}/po/${row.po_id}`)"
      @edit="row => { poDialogRecord = row; poDialogMode = 'edit'; poDialogVisible = true }"
      @approve="row => handleApprovePo(row)"
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

    <PoFormDialog
      v-model:visible="poDialogVisible"
      :mode="poDialogMode"
      :record="poDialogRecord"
      :vendors="vendors"
      @save="handlePoSave"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Download } from '@element-plus/icons-vue'
import { callApi } from '@/api/bridge.js'
import { usePo } from '@/composables/usePo.js'
import { useVendor } from '@/composables/useVendor.js'
import { useExport } from '@/composables/useExport.js'
import AdvancedFilterBar from '@/components/common/AdvancedFilterBar.vue'
import PoTable from '@/components/po/PoTable.vue'
import PoFormDialog from '@/components/po/PoFormDialog.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const { t } = useI18n()

const { state, searchPos, createPo, updatePo, approvePo, finishPo, setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange } = usePo()
const { state: vendorState, searchVendors } = useVendor()
const { exportAll } = useExport()
const exporting = ref(false)

const vendors = computed(() => vendorState.rows)

const poStatuses = [
  { label: t('status.pending'), value: 'po_pending' },
  { label: t('status.approved'), value: 'po_approved' },
  { label: t('status.finished'), value: 'finished' }
]

const poFilterConfig = [
  { name: 'status', label: t('filter.status'), type: 'select', options: poStatuses },
  { name: 'po_id', label: t('filter.poId'), type: 'input' },
  { name: 'po_no', label: t('filter.poNo'), type: 'input' },
  { name: 'sc_id', label: t('filter.scId'), type: 'input' },
  { name: 'vendor_id', label: t('filter.vendorId'), type: 'input' },
  { name: 'vendor_name', label: t('filter.vendorName'), type: 'input' },
  { name: 'po_amount', label: t('filter.poAmount'), type: 'amount-range' },
  { name: 'contract_from', label: t('filter.contractFrom'), type: 'date-range' },
  { name: 'contract_to', label: t('filter.contractTo'), type: 'date-range' },
]

const poDialogVisible = ref(false)
const poDialogMode = ref('create')
const poDialogRecord = ref(null)

function handleFilter({ text, filters }) {
  searchPos(text, filters)
}

function handleReset() {
  resetFilters()
  searchPos()
}

async function handleApprovePo(row) {
  try {
    await ElMessageBox.confirm(t('confirm.approvePo'), t('common.confirm'), { type: 'warning' })
    await approvePo(row.po_id)
    ElMessage.success(t('msg.poApproved'))
    await searchPos()
  } catch { /* cancelled */ }
}

async function handleFinishPo(row) {
  try {
    await ElMessageBox.confirm(t('confirm.finishPo'), t('common.confirm'), { type: 'warning' })
    await finishPo(row.po_id)
    ElMessage.success(t('msg.poFinished'))
    await searchPos()
  } catch { /* cancelled */ }
}

async function handlePoSave(data) {
  try {
    const { _attachments, ...formData } = data
    let poId, scId
    if (poDialogMode.value === 'create') {
      const created = await createPo(formData)
      poId = created.po_id
      scId = created.sc_id || formData.sc_id
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
      { key: 'po_amount', label: t('export.poAmount') },
      { key: 'open_po_amount', label: t('export.openPoAmount') },
      { key: 'contract_from', label: t('export.contractFrom'), getValue: r => (r.contract_from || '').slice(0, 10) },
      { key: 'contract_to', label: t('export.contractTo'), getValue: r => (r.contract_to || '').slice(0, 10) }
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
  await Promise.all([searchPos(), searchVendors()])
})
</script>
