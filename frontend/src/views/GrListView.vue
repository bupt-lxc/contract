<template>
  <div>
    <AdvancedFilterBar
      :filter-config="grFilterConfig"
      @filter="handleFilter"
      @reset="handleReset"
    />

    <el-table :data="state.rows" v-loading="state.loading" stripe border>
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
import { onMounted } from 'vue'
import { useGr } from '@/composables/useGr.js'
import AdvancedFilterBar from '@/components/common/AdvancedFilterBar.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'

const { state, searchGrs, setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange } = useGr()

const grStatuses = [
  { label: 'Pending', value: 'pending' }, { label: 'Approved', value: 'approved' }, { label: 'Cancelled', value: 'cancelled' }
]

const grFilterConfig = [
  { name: 'status', label: 'Status', type: 'select', options: grStatuses },
  { name: 'gr_id', label: 'GR ID', type: 'input' },
  { name: 'po_id', label: 'PO ID', type: 'input' },
  { name: 'sc_id', label: 'SC ID', type: 'input' },
  { name: 'requester_id', label: 'Requester', type: 'input' },
  { name: 'vendor_id', label: 'Vendor ID', type: 'input' },
  { name: 'estimated_amount', label: 'Est. Amount', type: 'amount-range' },
  { name: 'con_value', label: 'Con Value', type: 'amount-range' },
]

function handleFilter({ text, filters }) {
  searchGrs(text, filters)
}

function handleReset() {
  resetFilters()
  searchGrs()
}

function handlePageChange(page) { onPageChange(page); searchGrs() }
function handleSizeChange(size) { onPageSizeChange(size); searchGrs() }

onMounted(() => searchGrs())
</script>
