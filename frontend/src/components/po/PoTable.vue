<template>
  <el-table
    :data="rows"
    v-loading="loading"
    stripe
    border
    :row-class-name="rowClass"
  >
    <el-table-column :label="$t('po.status')" width="100">
      <template #default="{ row }"><StatusBadge :status="row.status" /></template>
    </el-table-column>
    <el-table-column prop="po_no" :label="$t('po.poNo')" width="130">
      <template #default="{ row }">{{ row.po_no || row.po_id }}</template>
    </el-table-column>
    <el-table-column prop="sc_id" :label="$t('filter.scId')" width="130" />
    <el-table-column prop="sc_no" :label="$t('filter.scNo')" width="130" />
    <el-table-column prop="requester_name" :label="$t('filter.requesterName')" width="130" show-overflow-tooltip />
    <el-table-column prop="vendor_name" :label="$t('po.vendor')" width="160" show-overflow-tooltip />
    <el-table-column prop="contract_type" :label="$t('po.contractType')" width="100" />
    <el-table-column prop="cost_center" :label="$t('po.costCenter')" width="110" />
    <el-table-column prop="po_amount" :label="$t('po.poAmount')" width="120">
      <template #default="{ row }"><AmountDisplay :value="row.po_amount" /></template>
    </el-table-column>
    <el-table-column prop="open_po_amount" :label="$t('po.openCon')" width="120">
      <template #default="{ row }"><AmountDisplay :value="row.open_po_amount" /></template>
    </el-table-column>
    <el-table-column prop="contract_from" :label="$t('po.contractFrom')" width="120">
      <template #default="{ row }">{{ formatDate(row.contract_from) }}</template>
    </el-table-column>
    <el-table-column prop="contract_to" :label="$t('po.contractTo')" width="120">
      <template #default="{ row }">{{ formatDate(row.contract_to) }}</template>
    </el-table-column>
    <el-table-column prop="activing_date" :label="$t('po.activingDate')" width="120">
      <template #default="{ row }">{{ formatDate(row.activing_date) }}</template>
    </el-table-column>
    <el-table-column :label="$t('po.actions')" width="200" fixed="right">
      <template #default="{ row }">
        <el-button type="primary" link size="small" @click.stop="$emit('detail', row)">{{ $t('common.detail') }}</el-button>
        <el-button type="primary" link size="small" @click.stop="$emit('edit', row)">{{ $t('po.edit') }}</el-button>
        <el-button v-if="row.status === 'draft'" type="primary" link size="small" @click.stop="$emit('submit', row)">{{ $t('common.submit') }}</el-button>
        <el-button v-if="row.status === 'activing'" type="info" link size="small" @click.stop="$emit('finish', row)">{{ $t('po.finish') }}</el-button>
      </template>
    </el-table-column>
    <template #empty><el-empty :description="$t('po.noRecords')" /></template>
  </el-table>
</template>

<script setup>
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'

defineProps({
  rows: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false }
})

defineEmits(['detail', 'edit', 'finish', 'submit'])

function rowClass({ row }) { return `status-row-${row.status || ''}` }
function formatDate(val) { return val ? val.slice(0, 10) : '-' }
</script>
