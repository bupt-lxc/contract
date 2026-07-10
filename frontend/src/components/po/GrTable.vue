<template>
  <el-table :data="rows" stripe border size="small" @row-click="row => $emit('row-click', row)" :default-sort="{ prop: 'created_at', order: 'descending' }">
    <el-table-column prop="status" :label="$t('gr.status')" width="90" sortable>
      <template #default="{ row }"><StatusBadge :status="row.status" /></template>
    </el-table-column>
    <el-table-column prop="gr_id" :label="$t('gr.id')" width="115" sortable>
      <template #default="{ row }">
        <el-tooltip :content="row.gr_id" placement="top" :disabled="!row.gr_id">
          <span class="mono-cell clickable">{{ shortId(row.gr_id) }}</span>
        </el-tooltip>
      </template>
    </el-table-column>
    <el-table-column prop="gr_no" :label="$t('gr.grNo')" width="105" sortable show-overflow-tooltip>
      <template #default="{ row }">{{ row.gr_no || '-' }}</template>
    </el-table-column>
    <el-table-column prop="requester_id" :label="$t('gr.requester')" width="95" sortable show-overflow-tooltip />
    <el-table-column prop="estimated_amount" :label="$t('gr.estimated')" width="105" sortable>
      <template #default="{ row }"><AmountDisplay :value="row.estimated_amount" /></template>
    </el-table-column>
    <el-table-column prop="tax_rate" :label="$t('gr.taxRate')" width="65" align="center" sortable>
      <template #default="{ row }">{{ row.tax_rate != null ? row.tax_rate + '%' : '-' }}</template>
    </el-table-column>
    <el-table-column prop="gross_cost" :label="$t('gr.grossCost')" width="110" sortable>
      <template #default="{ row }"><AmountDisplay :value="row.gross_cost" /></template>
    </el-table-column>
    <el-table-column prop="con_value" :label="$t('gr.conValue')" width="105" sortable>
      <template #default="{ row }"><AmountDisplay :value="row.con_value" /></template>
    </el-table-column>
    <el-table-column prop="goods_service_description" :label="$t('gr.goodsServiceDescription')" min-width="100" show-overflow-tooltip sortable>
      <template #default="{ row }">{{ row.goods_service_description || '-' }}</template>
    </el-table-column>
    <el-table-column prop="remark" :label="$t('gr.remark')" min-width="100" show-overflow-tooltip sortable />
    <el-table-column prop="is_cancellation" :label="$t('gr.isCancellation')" width="85" align="center" sortable>
      <template #default="{ row }">{{ row.is_cancellation === 'Y' ? $t('common.yes') : $t('common.no') }}</template>
    </el-table-column>
    <el-table-column prop="created_at" :label="$t('gr.created')" width="100" sortable>
      <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
    </el-table-column>
    <el-table-column prop="submitted_date" :label="$t('timestampLabel.submitted')" width="100" sortable>
      <template #default="{ row }">{{ formatDate(row.submitted_date) }}</template>
    </el-table-column>
    <el-table-column prop="confirmed_at" :label="$t('timestampLabel.confirmed')" width="100" sortable>
      <template #default="{ row }">{{ formatDate(row.confirmed_at) }}</template>
    </el-table-column>
    <el-table-column prop="pending_date" :label="$t('gr.pendingDate')" width="100" sortable>
      <template #default="{ row }">{{ formatDate(row.pending_date) }}</template>
    </el-table-column>
    <el-table-column prop="approved_date" :label="$t('gr.approvedDate')" width="100" sortable>
      <template #default="{ row }">{{ formatDate(row.approved_date) }}</template>
    </el-table-column>
    <el-table-column prop="finished_at" :label="$t('timestampLabel.finished')" width="100" sortable>
      <template #default="{ row }">{{ formatDate(row.finished_at) }}</template>
    </el-table-column>
    <el-table-column prop="updated_at" :label="$t('timestampLabel.updated')" width="100" sortable>
      <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
    </el-table-column>
    <el-table-column :label="$t('gr.actions')" width="250" fixed="right">
      <template #default="{ row }">
        <el-button type="primary" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('detail', row)">{{ $t('common.detail') }}</el-button>
        <el-button type="primary" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('edit', row)">{{ $t('gr.edit') }}</el-button>
        <el-button v-if="row.status === 'draft'" type="primary" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('submit', row)">{{ $t('common.submit') }}</el-button>
        <el-button v-if="row.status === 'approved'" type="success" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('finish', row)">{{ $t('gr.finishGr') }}</el-button>
        <el-button v-if="row.status === 'pending'" type="success" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('approve', row)">{{ $t('gr.approve') }}</el-button>
        <el-popconfirm v-if="row.status === 'pending'" :title="$t('gr.denyConfirm')" @confirm="$emit('deny', row)">
          <template #reference>
            <el-button type="danger" link size="small" :disabled="loadingState.count > 0" @click.stop>{{ $t('gr.deny') }}</el-button>
          </template>
        </el-popconfirm>
        <el-button type="info" link size="small" :disabled="loadingState.count > 0" @click.stop="$emit('attachments', row)">
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
import { loadingState } from '@/api/bridge.js'
import { formatDateTime } from '@/utils/format.js'

defineProps({ rows: { type: Array, default: () => [] } })
defineEmits(['detail', 'edit', 'approve', 'deny', 'finish', 'attachments', 'row-click', 'submit'])

function shortId(id) { if (!id) return '-'; const parts = id.split('-'); return parts.slice(2).join('-') }
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
</style>
