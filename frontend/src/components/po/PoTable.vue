<template>
  <el-table
    :data="rows"
    v-loading="loading"
    stripe
    border
    @row-click="$emit('row-click', $event)"
    :row-class-name="rowClass"
    style="cursor:pointer"
  >
    <el-table-column label="Status" width="100">
      <template #default="{ row }"><StatusBadge :status="row.status" /></template>
    </el-table-column>
    <el-table-column prop="po_no" label="PO No" width="130">
      <template #default="{ row }">{{ row.po_no || row.po_id }}</template>
    </el-table-column>
    <el-table-column prop="vendor_name" label="Vendor" width="160" show-overflow-tooltip />
    <el-table-column prop="po_amount" label="PO Amount" width="120">
      <template #default="{ row }"><AmountDisplay :value="row.po_amount" /></template>
    </el-table-column>
    <el-table-column prop="open_po_amount" label="Open/Con" width="120">
      <template #default="{ row }"><AmountDisplay :value="row.open_po_amount" /></template>
    </el-table-column>
    <el-table-column prop="contract_from" label="Contract From" width="120">
      <template #default="{ row }">{{ formatDate(row.contract_from) }}</template>
    </el-table-column>
    <el-table-column prop="contract_to" label="Contract To" width="120">
      <template #default="{ row }">{{ formatDate(row.contract_to) }}</template>
    </el-table-column>
    <el-table-column label="Actions" width="140" fixed="right">
      <template #default="{ row }">
        <el-button type="primary" link size="small" @click.stop="$emit('edit', row)">Edit</el-button>
        <el-button v-if="row.status === 'po_pending'" type="success" link size="small" @click.stop="$emit('approve', row)">Approve</el-button>
        <el-button v-if="row.status === 'po_approved'" type="info" link size="small" @click.stop="$emit('finish', row)">Finish</el-button>
      </template>
    </el-table-column>
    <template #empty><el-empty description="No PO records." /></template>
  </el-table>
</template>

<script setup>
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'

defineProps({
  rows: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false }
})

defineEmits(['row-click', 'edit', 'approve', 'finish'])

function rowClass({ row }) { return `status-row-${row.status || ''}` }
function formatDate(val) { return val ? val.slice(0, 10) : '-' }
</script>
