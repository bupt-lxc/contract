<template>
  <div>
    <FilterBar @reset="handleReset">
      <template #filters>
        <el-select v-model="filters.status" placeholder="Status" clearable @change="onFilterChange">
          <el-option v-for="s in poStatuses" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-date-picker v-model="filters.contract_to" type="date" placeholder="Contract To" value-format="YYYY-MM-DD" @change="onFilterChange" />
        <el-select v-model="filters.open_po" placeholder="OPEN PO" clearable @change="onFilterChange">
          <el-option label="Open" value="open" />
          <el-option label="Closed" value="closed" />
        </el-select>
      </template>
    </FilterBar>

    <PoTable
      :rows="filteredRows"
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
import { ref, reactive, computed, onMounted } from 'vue'
import { usePo } from '@/composables/usePo.js'
import { useVendor } from '@/composables/useVendor.js'
import FilterBar from '@/components/common/FilterBar.vue'
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

const filters = reactive({ status: '', contract_to: '', open_po: '' })
const poDialogVisible = ref(false)
const poDialogMode = ref('create')
const poDialogRecord = ref(null)

const filteredRows = computed(() => {
  let rows = state.rows
  if (filters.contract_to) {
    rows = rows.filter(r => r.contract_to?.slice(0, 10) === filters.contract_to)
  }
  if (filters.open_po === 'open') {
    rows = rows.filter(r => (r.open_po_amount || r.po_amount || 0) > 0)
  } else if (filters.open_po === 'closed') {
    rows = rows.filter(r => (r.open_po_amount || 0) <= 0)
  }
  return rows
})

function onFilterChange() {
  const f = {}
  if (filters.status) f.status = filters.status
  setFilters(f)
  searchPos(null, f)
}

function handleReset() {
  Object.assign(filters, { status: '', contract_to: '', open_po: '' })
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
      await updatePo(data)
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
