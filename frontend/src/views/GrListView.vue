<template>
  <div>
    <FilterBar @reset="handleReset">
      <template #filters>
        <el-select v-model="filters.status" placeholder="Status" clearable @change="onFilterChange">
          <el-option v-for="s in grStatuses" :key="s.label" :label="s.label" :value="s.value" />
        </el-select>
        <el-input-number v-model="filters.amount_min" placeholder="Amount min" :min="0" controls-position="right" @change="onFilterChange" style="width:160px" />
        <el-input-number v-model="filters.amount_max" placeholder="Amount max" :min="0" controls-position="right" @change="onFilterChange" style="width:160px" />
      </template>
    </FilterBar>

    <el-table :data="filteredRows" v-loading="state.loading" stripe border>
      <el-table-column label="Status" width="100">
        <template #default="{ row }"><StatusBadge :status="row.status" /></template>
      </el-table-column>
      <el-table-column prop="gr_id" label="GR ID" width="120" />
      <el-table-column prop="po_no" label="PO No" width="130" />
      <el-table-column prop="sc_no" label="SC No" width="130" />
      <el-table-column prop="vendor_name" label="Vendor" min-width="150" show-overflow-tooltip />
      <el-table-column prop="estimated_amount" label="Estimated" width="120">
        <template #default="{ row }"><AmountDisplay :value="row.estimated_amount" /></template>
      </el-table-column>
      <el-table-column prop="con_value" label="Con Value" width="120">
        <template #default="{ row }"><AmountDisplay :value="row.con_value" /></template>
      </el-table-column>
      <template #empty><el-empty description="No GR records found." /></template>
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
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useGr } from '@/composables/useGr.js'
import FilterBar from '@/components/common/FilterBar.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'

const { state, searchGrs, setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange } = useGr()

const grStatuses = [
  { label: 'Pending', value: 'pending' }, { label: 'Approved', value: 'approved' }, { label: 'Cancelled', value: 'cancelled' }
]

const filters = reactive({ status: '', amount_min: null, amount_max: null })

const filteredRows = computed(() => {
  let rows = state.rows
  if (filters.amount_min != null) {
    rows = rows.filter(r => (Number(r.estimated_amount) || 0) >= filters.amount_min)
  }
  if (filters.amount_max != null) {
    rows = rows.filter(r => (Number(r.estimated_amount) || 0) <= filters.amount_max)
  }
  return rows
})

function onFilterChange() {
  const f = {}
  if (filters.status) f.status = filters.status
  setFilters(f)
  searchGrs(null, f)
}

function handleReset() {
  Object.assign(filters, { status: '', amount_min: null, amount_max: null })
  resetFilters()
  searchGrs()
}

function handlePageChange(page) { onPageChange(page); searchGrs() }
function handleSizeChange(size) { onPageSizeChange(size); searchGrs() }

onMounted(() => searchGrs())
</script>
