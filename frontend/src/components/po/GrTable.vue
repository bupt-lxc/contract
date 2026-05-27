<template>
  <el-table :data="rows" stripe border style="width:100%">
    <el-table-column label="Status" width="100">
      <template #default="{ row }"><StatusBadge :status="row.status" /></template>
    </el-table-column>
    <el-table-column prop="gr_id" label="GR ID" width="120" />
    <el-table-column prop="requester_id" label="Requester" width="120" />
    <el-table-column prop="estimated_amount" label="Estimated" width="120">
      <template #default="{ row }"><AmountDisplay :value="row.estimated_amount" /></template>
    </el-table-column>
    <el-table-column prop="con_value" label="Con Value" width="120">
      <template #default="{ row }"><AmountDisplay :value="row.con_value" /></template>
    </el-table-column>
    <el-table-column prop="remark" label="Remark" min-width="140" show-overflow-tooltip />
    <el-table-column prop="created_at" label="Created" width="110">
      <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
    </el-table-column>
    <el-table-column label="Actions" width="180" fixed="right">
      <template #default="{ row }">
        <el-button type="primary" link size="small" @click="$emit('edit', row)">Edit</el-button>
        <el-button v-if="row.status === 'pending'" type="success" link size="small" @click="$emit('approve', row)">Approve</el-button>
        <el-popconfirm v-if="row.status === 'pending'" title="Cancel this GR?" @confirm="$emit('cancel', row)">
          <template #reference>
            <el-button type="danger" link size="small">Cancel</el-button>
          </template>
        </el-popconfirm>
      </template>
    </el-table-column>
    <template #empty><el-empty description="No GRs for this PO." /></template>
  </el-table>
</template>

<script setup>
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'

defineProps({ rows: { type: Array, default: () => [] } })
defineEmits(['edit', 'approve', 'cancel'])

function formatDate(val) { return val ? val.slice(0, 10) : '-' }
</script>
