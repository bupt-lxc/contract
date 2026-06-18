<template>
  <el-table :data="rows" stripe border style="width:100%" @row-click="row => $emit('row-click', row)" :default-sort="{ prop: 'created_at', order: 'descending' }">
    <el-table-column prop="status" :label="$t('gr.status')" width="100" sortable>
      <template #default="{ row }"><StatusBadge :status="row.status" /></template>
    </el-table-column>
    <el-table-column prop="gr_id" :label="$t('gr.id')" width="120" sortable />
    <el-table-column prop="gr_no" :label="$t('gr.grNo')" width="120" sortable>
      <template #default="{ row }">{{ row.gr_no || '-' }}</template>
    </el-table-column>
    <el-table-column prop="requester_id" :label="$t('gr.requester')" width="120" sortable />
    <el-table-column prop="estimated_amount" :label="$t('gr.estimated')" width="120" sortable>
      <template #default="{ row }"><AmountDisplay :value="row.estimated_amount" /></template>
    </el-table-column>
    <el-table-column prop="tax_rate" :label="$t('gr.taxRate')" width="80" align="center" sortable>
      <template #default="{ row }">{{ row.tax_rate != null ? row.tax_rate + '%' : '-' }}</template>
    </el-table-column>
    <el-table-column prop="gross_cost" :label="$t('gr.grossCost')" width="130" sortable>
      <template #default="{ row }"><AmountDisplay :value="row.gross_cost" /></template>
    </el-table-column>
    <el-table-column prop="con_value" :label="$t('gr.conValue')" width="120" sortable>
      <template #default="{ row }"><AmountDisplay :value="row.con_value" /></template>
    </el-table-column>
    <el-table-column prop="remark" :label="$t('gr.remark')" min-width="140" show-overflow-tooltip sortable />
    <el-table-column prop="created_at" :label="$t('gr.created')" width="110" sortable>
      <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
    </el-table-column>
    <el-table-column prop="pending_date" :label="$t('gr.pendingDate')" width="110" sortable>
      <template #default="{ row }">{{ formatDate(row.pending_date) }}</template>
    </el-table-column>
    <el-table-column prop="approved_date" :label="$t('gr.approvedDate')" width="110" sortable>
      <template #default="{ row }">{{ formatDate(row.approved_date) }}</template>
    </el-table-column>
    <el-table-column :label="$t('gr.actions')" width="280" fixed="right">
      <template #default="{ row }">
        <el-button type="primary" link size="small" @click.stop="$emit('detail', row)">{{ $t('common.detail') }}</el-button>
        <el-button type="primary" link size="small" @click.stop="$emit('edit', row)">{{ $t('gr.edit') }}</el-button>
        <el-button v-if="row.status === 'draft'" type="primary" link size="small" @click.stop="$emit('submit', row)">{{ $t('common.submit') }}</el-button>
        <el-button v-if="row.status === 'pending'" type="success" link size="small" @click.stop="$emit('approve', row)">{{ $t('gr.approve') }}</el-button>
        <el-popconfirm v-if="row.status === 'pending'" :title="$t('gr.cancelConfirm')" @confirm="$emit('cancel', row)">
          <template #reference>
            <el-button type="danger" link size="small" @click.stop>{{ $t('gr.cancel') }}</el-button>
          </template>
        </el-popconfirm>
        <el-button type="info" link size="small" @click.stop="$emit('attachments', row)">
          <el-icon><Paperclip /></el-icon>
        </el-button>
      </template>
    </el-table-column>
    <template #empty><el-empty :description="$t('gr.noRecordsForPo')" /></template>
  </el-table>
</template>

<script setup>
import { Paperclip } from '@element-plus/icons-vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'

defineProps({ rows: { type: Array, default: () => [] } })
defineEmits(['detail', 'edit', 'approve', 'cancel', 'attachments', 'row-click', 'submit'])

function formatDate(val) { return val ? val.slice(0, 10) : '-' }
</script>
