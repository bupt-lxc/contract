<template>
  <div>
    <AdvancedFilterBar
      :filter-config="poFilterConfig"
      @filter="handleFilter"
      @reset="handleReset"
    />

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
import { usePo } from '@/composables/usePo.js'
import { useVendor } from '@/composables/useVendor.js'
import AdvancedFilterBar from '@/components/common/AdvancedFilterBar.vue'
import PoTable from '@/components/po/PoTable.vue'
import PoFormDialog from '@/components/po/PoFormDialog.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const { state, searchPos, createPo, updatePo, approvePo, finishPo, setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange } = usePo()
const { state: vendorState, searchVendors } = useVendor()

const vendors = computed(() => vendorState.rows)

const poStatuses = [
  { label: 'Pending', value: 'po_pending' }, { label: 'Approved', value: 'po_approved' },
  { label: 'Finished', value: 'finished' }
]

const poFilterConfig = [
  { name: 'status', label: 'Status', type: 'select', options: poStatuses },
  { name: 'po_id', label: 'PO ID', type: 'input' },
  { name: 'po_no', label: 'PO No', type: 'input' },
  { name: 'sc_id', label: 'SC ID', type: 'input' },
  { name: 'vendor_id', label: 'Vendor ID', type: 'input' },
  { name: 'vendor_name', label: 'Vendor Name', type: 'input' },
  { name: 'po_amount', label: 'PO Amount', type: 'amount-range' },
  { name: 'contract_from', label: 'Contract From', type: 'date-range' },
  { name: 'contract_to', label: 'Contract To', type: 'date-range' },
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
    await ElMessageBox.confirm('Approve this PO?', 'Confirm', { type: 'warning' })
    await approvePo(row.po_id)
    ElMessage.success('PO approved')
    await searchPos()
  } catch { /* cancelled */ }
}

async function handleFinishPo(row) {
  try {
    await ElMessageBox.confirm('Finish this PO?', 'Confirm', { type: 'warning' })
    await finishPo(row.po_id)
    ElMessage.success('PO finished')
    await searchPos()
  } catch { /* cancelled */ }
}

async function handlePoSave(data) {
  try {
    if (poDialogMode.value === 'create') {
      await createPo(data)
    } else {
      await updatePo(poDialogRecord.value?.po_id, data)
    }
    await searchPos()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}

function handlePageChange(page) { onPageChange(page); searchPos() }
function handleSizeChange(size) { onPageSizeChange(size); searchPos() }

onMounted(async () => {
  await Promise.all([searchPos(), searchVendors()])
})
</script>
