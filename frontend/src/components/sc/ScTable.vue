<template>
  <el-table
    :data="rows"
    v-loading="loading"
    stripe
    border
    @sort-change="$emit('sort-change', $event)"
    @row-click="$emit('row-click', $event)"
    @selection-change="$emit('selection-change', $event)"
    :row-class-name="rowClass"
    style="cursor:pointer"
  >
    <el-table-column v-if="selectable" type="selection" width="50" />
    <el-table-column :label="$t('sc.status')" width="100">
      <template #default="{ row }">
        <StatusBadge :status="row.status" />
      </template>
    </el-table-column>
    <el-table-column prop="sc_no" :label="$t('sc.scNo')" sortable="custom" width="130" />
    <el-table-column prop="requester_name" :label="$t('sc.requester')" sortable="custom" width="130" />
    <el-table-column prop="request_type" :label="$t('sc.type')" sortable="custom" width="110" />
    <el-table-column prop="cost_center" :label="$t('sc.costCenter')" sortable="custom" width="110" />
    <el-table-column prop="asset" :label="$t('sc.asset')" sortable="custom" width="70" />
    <el-table-column prop="sc_amount" :label="$t('sc.scAmount')" sortable="custom" width="130">
      <template #default="{ row }">
        <AmountDisplay :value="row.sc_amount" />
      </template>
    </el-table-column>
    <el-table-column prop="created_at" :label="$t('sc.created')" sortable="custom" width="120">
      <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
    </el-table-column>
    <el-table-column prop="pending_date" :label="$t('sc.pendingDate')" sortable="custom" width="120">
      <template #default="{ row }">{{ formatDate(row.pending_date) }}</template>
    </el-table-column>
    <el-table-column prop="approved_date" :label="$t('sc.approvedDate')" sortable="custom" width="120">
      <template #default="{ row }">{{ formatDate(row.approved_date) }}</template>
    </el-table-column>
    <el-table-column prop="description" :label="$t('sc.description')" min-width="150" show-overflow-tooltip />
    <el-table-column :label="$t('common.actions')" width="70" fixed="right">
      <template #default>
        <el-button type="primary" link size="small">{{ $t('common.detail') }}</el-button>
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
  emptyText: { type: String, default: 'No SC records match the search and filters.' },
  selectable: { type: Boolean, default: false }
})

defineEmits(['sort-change', 'row-click', 'selection-change'])

function rowClass({ row }) {
  return `status-row-${row.status || ''}`
}

function formatDate(val) {
  if (!val) return '-'
  return val.slice(0, 10)
}
</script>
