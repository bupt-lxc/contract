<template>
  <el-table
    :data="rows"
    v-loading="loading"
    stripe
    border
    @sort-change="$emit('sort-change', $event)"
    @selection-change="$emit('selection-change', $event)"
    :row-class-name="rowClass"
  >
    <el-table-column v-if="selectable" type="selection" width="50" />
    <el-table-column :label="$t('sc.status')" width="100">
      <template #default="{ row }">
        <StatusBadge :status="row.status" />
      </template>
    </el-table-column>
    <el-table-column prop="sc_no" :label="$t('sc.scNo')" sortable="custom" width="130">
      <template #default="{ row }">
        <span style="font-family:monospace;font-size:12px">{{ row.sc_no || '-' }}</span>
      </template>
    </el-table-column>
    <el-table-column prop="sc_id" :label="$t('sc.scId')" sortable="custom" width="135">
      <template #default="{ row }">
        <el-tooltip :content="row.sc_id" placement="top" :disabled="!row.sc_id">
          <span style="font-family:monospace;font-size:12px;cursor:default">{{ shortScId(row.sc_id) }}</span>
        </el-tooltip>
      </template>
    </el-table-column>
    <el-table-column prop="requester_name" :label="$t('sc.requester')" sortable="custom" width="130" />
    <el-table-column :label="$t('sc.type')" sortable="custom" width="140">
      <template #default="{ row }">
        <span>{{ requestTypeLabel(row.request_type) || '-' }}</span>
        <el-tag v-if="row.calloff_po_id" type="warning" size="small" style="margin-left:4px">
          {{ $t('sc.calloffBadge') }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="cost_center" :label="$t('sc.costCenter')" sortable="custom" width="110" />
    <el-table-column prop="service_scope" :label="$t('vendor.serviceScope')" width="150">
      <template #default="{ row }">
        <span>{{ row.service_scope || '-' }}</span>
      </template>
    </el-table-column>
    <el-table-column prop="asset" :label="$t('sc.asset')" sortable="custom" width="70" />
    <el-table-column prop="sc_amount" :label="$t('sc.scAmount')" sortable="custom" width="130">
      <template #default="{ row }">
        <AmountDisplay :value="row.sc_amount" />
      </template>
    </el-table-column>
    <el-table-column prop="service_period_start" :label="$t('sc.startDate')" sortable="custom" width="120">
      <template #default="{ row }">{{ formatDate(row.service_period_start) }}</template>
    </el-table-column>
    <el-table-column prop="service_period_end" :label="$t('sc.endDate')" sortable="custom" width="120">
      <template #default="{ row }">{{ formatDate(row.service_period_end) }}</template>
    </el-table-column>
    <el-table-column prop="created_at" :label="$t('sc.created')" sortable="custom" width="120">
      <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
    </el-table-column>
    <el-table-column prop="submitted_date" :label="$t('sc.submittedDate')" sortable="custom" width="120">
      <template #default="{ row }">{{ formatDate(row.submitted_date) }}</template>
    </el-table-column>
    <el-table-column prop="confirmed_at" :label="$t('timestampLabel.confirmed')" sortable="custom" width="120">
      <template #default="{ row }">{{ formatDate(row.confirmed_at) }}</template>
    </el-table-column>
    <el-table-column prop="pending_date" :label="$t('sc.pendingDate')" sortable="custom" width="120">
      <template #default="{ row }">{{ formatDate(row.pending_date) }}</template>
    </el-table-column>
    <el-table-column prop="approved_date" :label="$t('sc.approvedDate')" sortable="custom" width="120">
      <template #default="{ row }">{{ formatDate(row.approved_date) }}</template>
    </el-table-column>
    <el-table-column prop="finished_at" :label="$t('timestampLabel.finished')" sortable="custom" width="120">
      <template #default="{ row }">{{ formatDate(row.finished_at) }}</template>
    </el-table-column>
    <el-table-column prop="updated_at" :label="$t('timestampLabel.updated')" sortable="custom" width="120">
      <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
    </el-table-column>
    <el-table-column prop="description" :label="$t('sc.description')" min-width="150" show-overflow-tooltip />
    <el-table-column :label="$t('common.actions')" width="70" fixed="right">
      <template #default="{ row }">
        <el-button type="primary" link size="small" @click.stop="$emit('detail', row)">{{ $t('common.detail') }}</el-button>
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
import { requestTypeLabel } from '@/composables/useRequestType.js'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  emptyText: { type: String, default: 'No SC records match the search and filters.' },
  selectable: { type: Boolean, default: false }
})

defineEmits(['sort-change', 'detail', 'selection-change'])

function rowClass({ row }) {
  return `status-row-${row.status || ''}`
}

function shortScId(scId) {
  if (!scId) return '-'
  const parts = scId.split('-')
  return parts.slice(2).join('-')
}

function formatDate(val) {
  if (!val) return '-'
  return val.slice(0, 10)
}
</script>
