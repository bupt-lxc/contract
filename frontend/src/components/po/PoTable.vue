<template>
  <el-table
    :data="rows"
    v-loading="loading"
    stripe
    border
    size="small"
    :row-class-name="rowClass"
    :default-sort="{ prop: 'po_no', order: 'ascending' }"
    @selection-change="val => $emit('selection-change', val)"
    @sort-change="(sort) => $emit('sort-change', sort)"
  >
    <el-table-column v-if="selectable" type="selection" width="40" />
    <el-table-column prop="status" :label="$t('po.status')" width="90" sortable="custom">
      <template #default="{ row }"><StatusBadge :status="row.status" /></template>
    </el-table-column>
    <el-table-column prop="po_no" :label="$t('po.poNo')" width="115" sortable="custom">
      <template #default="{ row }">
        <template v-if="row.po_no">{{ row.po_no }}</template>
        <el-tooltip v-else :content="row.po_id" placement="top">
          <span class="mono-cell clickable">{{ shortId(row.po_id) }}</span>
        </el-tooltip>
      </template>
    </el-table-column>
    <el-table-column v-if="!hideScInfo" prop="sc_no" :label="$t('filter.scNo')" width="115" sortable="custom" show-overflow-tooltip>
      <template #default="{ row }">{{ row.sc_no || '-' }}</template>
    </el-table-column>
    <el-table-column v-if="!hideScInfo" prop="sc_id" :label="$t('filter.scId')" width="115">
      <template #default="{ row }">
        <el-tooltip :content="row.sc_id" placement="top" :disabled="!row.sc_id">
          <span class="mono-cell clickable">{{ shortId(row.sc_id) }}</span>
        </el-tooltip>
      </template>
    </el-table-column>
    <el-table-column v-if="!hideScInfo" prop="requester_name" :label="$t('filter.requesterName')" width="100" show-overflow-tooltip sortable="custom" />
    <el-table-column prop="vendor_name" :label="$t('po.vendor')" width="140" show-overflow-tooltip sortable="custom">
      <template #default="{ row }">
        <span>{{ row.vendor_name || '-' }}</span>
        <span v-if="row.ksrm_vendor_code" class="ksrm-code">{{ row.ksrm_vendor_code }}</span>
      </template>
    </el-table-column>
    <el-table-column :label="$t('sc.type')" width="60" align="center">
      <template #default="{ row }">
        <el-tag v-if="row.sc_request_type === 'FC'" type="info" size="small">FC</el-tag>
        <span v-else>—</span>
      </template>
    </el-table-column>
    <el-table-column prop="contract_type" :label="$t('po.contractType')" width="90" sortable="custom" />
    <el-table-column prop="contract_no" :label="$t('po.contractNo')" width="115" show-overflow-tooltip>
      <template #default="{ row }">{{ row.contract_no || '-' }}</template>
    </el-table-column>
    <el-table-column prop="contract_from" :label="$t('po.startDate')" width="100">
      <template #default="{ row }">{{ formatDate(row.contract_from) }}</template>
    </el-table-column>
    <el-table-column prop="contract_to" :label="$t('po.contractEndDate')" width="100" sortable="custom">
      <template #default="{ row }">{{ formatDate(row.contract_to) }}</template>
    </el-table-column>
    <el-table-column prop="active_date" :label="$t('po.activeDate')" width="100" sortable="custom">
      <template #default="{ row }">{{ formatDate(row.active_date) }}</template>
    </el-table-column>
    <el-table-column prop="payment_frequency" :label="$t('po.paymentFrequency')" width="95">
      <template #default="{ row }">{{ row.payment_frequency || '-' }}</template>
    </el-table-column>
    <el-table-column prop="contract_pos" :label="$t('po.contractPos')" width="90">
      <template #default="{ row }">{{ row.contract_pos || '-' }}</template>
    </el-table-column>
    <el-table-column prop="cost_center" :label="$t('po.costCenter')" width="95" sortable="custom" />
    <el-table-column prop="purchaser" :label="$t('po.purchaser')" width="95" show-overflow-tooltip>
      <template #default="{ row }">{{ row.purchaser || '-' }}</template>
    </el-table-column>
    <el-table-column prop="po_amount" :label="$t('po.poAmount')" width="110" sortable="custom">
      <template #default="{ row }"><AmountDisplay :value="row.po_amount" /></template>
    </el-table-column>
    <el-table-column prop="open_po_amount" :label="$t('po.openCon')" width="110">
      <template #default="{ row }"><AmountDisplay :value="row.open_po_amount" /></template>
    </el-table-column>
    <el-table-column prop="po_pending_total_incl_tax" :label="$t('po.pendingInclTax')" width="120">
      <template #default="{ row }"><AmountDisplay :value="row.po_pending_total_incl_tax" /></template>
    </el-table-column>
    <el-table-column prop="consumed_amount" :label="$t('po.consumedAmount')" width="115">
      <template #default="{ row }"><AmountDisplay :value="row.consumed_amount" /></template>
    </el-table-column>
    <el-table-column prop="created_at" :label="$t('timestampLabel.created')" width="100" sortable="custom">
      <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
    </el-table-column>
    <el-table-column prop="finished_at" :label="$t('timestampLabel.finished')" width="100">
      <template #default="{ row }">{{ formatDate(row.finished_at) }}</template>
    </el-table-column>
    <el-table-column prop="updated_at" :label="$t('timestampLabel.updated')" width="100" sortable="custom">
      <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
    </el-table-column>
    <el-table-column :label="$t('po.actions')" width="180" fixed="right">
      <template #default="{ row }">
        <el-button type="primary" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('detail', row)">{{ $t('common.detail') }}</el-button>
        <el-button type="primary" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('edit', row)">{{ $t('po.edit') }}</el-button>
        <el-button v-if="row.status === 'draft'" type="primary" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('submit', row)">{{ $t('common.submit') }}</el-button>
        <el-button v-if="row.status === 'active'" type="info" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('finish', row)">{{ $t('po.finish') }}</el-button>
      </template>
    </el-table-column>
    <template #empty><el-empty :description="$t('po.noRecords')" /></template>
  </el-table>
</template>

<script setup>
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'
import { loadingState } from '@/api/bridge.js'

defineProps({
  rows: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  hideScInfo: { type: Boolean, default: false },
  selectable: { type: Boolean, default: false }
})

defineEmits(['detail', 'edit', 'finish', 'submit', 'selection-change', 'sort-change'])

function shortId(id) { if (!id) return '-'; const parts = id.split('-'); return parts.slice(2).join('-') }
function rowClass({ row }) { return `status-row-${row.status || ''}` }
function formatDate(val) { return val ? val.slice(0, 10) : '-' }
</script>

<style scoped>
.mono-cell {
  font-family: 'Cascadia Code', 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 11px;
}
.mono-cell.clickable {
  cursor: default;
}
.ksrm-code {
  color: #94a3b8;
  font-size: 11px;
  margin-left: 4px;
}
.ksrm-code::before {
  content: '(';
}
.ksrm-code::after {
  content: ')';
}
</style>
