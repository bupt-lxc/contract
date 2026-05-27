<template>
  <el-table
    :data="rows"
    v-loading="loading"
    stripe
    border
    @sort-change="$emit('sort-change', $event)"
    @row-click="$emit('row-click', $event)"
    :row-class-name="rowClass"
    style="cursor:pointer"
  >
    <el-table-column label="Status" width="100">
      <template #default="{ row }">
        <StatusBadge :status="row.status" />
      </template>
    </el-table-column>
    <el-table-column prop="sc_no" label="SC No" sortable="custom" width="130" />
    <el-table-column prop="requester_name" label="Requester" sortable="custom" width="130" />
    <el-table-column prop="request_type" label="Type" sortable="custom" width="110" />
    <el-table-column prop="cost_center" label="Cost Center" sortable="custom" width="110" />
    <el-table-column prop="sc_amount" label="SC Amount" sortable="custom" width="130">
      <template #default="{ row }">
        <AmountDisplay :value="row.sc_amount" />
      </template>
    </el-table-column>
    <el-table-column prop="created_at" label="Created" sortable="custom" width="120">
      <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
    </el-table-column>
    <el-table-column prop="description" label="Description" min-width="150" show-overflow-tooltip />
    <el-table-column label="Actions" width="70" fixed="right">
      <template #default>
        <el-button type="primary" link size="small">Detail</el-button>
      </template>
    </el-table-column>
    <template #empty>
      <el-empty :description="emptyText" />
    </template>
  </el-table>
</template>

<script setup>
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  emptyText: { type: String, default: 'No SC records match the search and filters.' }
})

defineEmits(['sort-change', 'row-click'])

function rowClass({ row }) {
  return `status-row-${row.status || ''}`
}

function formatDate(val) {
  if (!val) return '-'
  return val.slice(0, 10)
}
</script>
