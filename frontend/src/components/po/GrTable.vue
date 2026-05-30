<template>
  <el-table :data="rows" stripe border style="width:100%">
    <el-table-column :label="$t('gr.status')" width="100">
      <template #default="{ row }"><StatusBadge :status="row.status" /></template>
    </el-table-column>
    <el-table-column prop="gr_id" :label="$t('gr.id')" width="120" />
    <el-table-column prop="requester_id" :label="$t('gr.requester')" width="120" />
    <el-table-column prop="estimated_amount" :label="$t('gr.estimated')" width="120">
      <template #default="{ row }"><AmountDisplay :value="row.estimated_amount" /></template>
    </el-table-column>
    <el-table-column prop="con_value" :label="$t('gr.conValue')" width="120">
      <template #default="{ row }"><AmountDisplay :value="row.con_value" /></template>
    </el-table-column>
    <el-table-column prop="remark" :label="$t('gr.remark')" min-width="140" show-overflow-tooltip />
    <el-table-column prop="created_at" :label="$t('gr.created')" width="110">
      <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
    </el-table-column>
    <el-table-column :label="$t('gr.actions')" width="180" fixed="right">
      <template #default="{ row }">
        <el-button type="primary" link size="small" @click="$emit('edit', row)">{{ $t('gr.edit') }}</el-button>
        <el-button v-if="row.status === 'pending'" type="success" link size="small" @click="$emit('approve', row)">{{ $t('gr.approve') }}</el-button>
        <el-popconfirm v-if="row.status === 'pending'" :title="$t('gr.cancelConfirm')" @confirm="$emit('cancel', row)">
          <template #reference>
            <el-button type="danger" link size="small">{{ $t('gr.cancel') }}</el-button>
          </template>
        </el-popconfirm>
      </template>
    </el-table-column>
    <template #empty><el-empty :description="$t('gr.noRecordsForPo')" /></template>
  </el-table>
</template>

<script setup>
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'

defineProps({ rows: { type: Array, default: () => [] } })
defineEmits(['edit', 'approve', 'cancel'])

function formatDate(val) { return val ? val.slice(0, 10) : '-' }
</script>
