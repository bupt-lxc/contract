<template>
  <el-card class="budget-card">
    <template #header>Budget Summary</template>
    <el-descriptions :column="3" border size="small">
      <el-descriptions-item :label="$t('sc.scAmount')">
        <AmountDisplay :value="budget.sc_amount" />
      </el-descriptions-item>
      <el-descriptions-item :label="$t('sc.allocatedPo')">
        <AmountDisplay :value="budget.allocated_po_amount" />
      </el-descriptions-item>
      <el-descriptions-item :label="$t('sc.unallocated')">
        <AmountDisplay :value="budget.unallocated_sc_amount" />
      </el-descriptions-item>

      <template v-if="isFC">
        <el-descriptions-item :label="$t('sc.downstreamCalloff')">
          <AmountDisplay :value="budget.downstream_calloff_amount" />
        </el-descriptions-item>
        <el-descriptions-item :label="$t('sc.pendingCalloff')">
          <AmountDisplay :value="budget.pending_calloff_amount" />
        </el-descriptions-item>
        <el-descriptions-item :label="$t('po.downstreamConsumed')">
          <AmountDisplay :value="budget.downstream_consumed" />
        </el-descriptions-item>
        <el-descriptions-item :label="$t('po.downstreamPendingGr') + ' (excl)'">
          <AmountDisplay :value="budget.downstream_pending_gr" />
        </el-descriptions-item>
        <el-descriptions-item :label="$t('po.downstreamPendingGr') + ' (incl)'">
          <AmountDisplay :value="budget.downstream_pending_gr_tax" />
        </el-descriptions-item>
      </template>
      <template v-else>
        <el-descriptions-item label="Consumed">
          <AmountDisplay :value="budget.sc_con_value_total" />
        </el-descriptions-item>
        <el-descriptions-item label="Pending GR (excl)">
          <AmountDisplay :value="budget.sc_pending_total" />
        </el-descriptions-item>
        <el-descriptions-item label="Pending GR (incl)">
          <AmountDisplay :value="budget.sc_pending_total_incl_tax" />
        </el-descriptions-item>
      </template>
    </el-descriptions>
  </el-card>
</template>

<script setup>
import AmountDisplay from '@/components/common/AmountDisplay.vue'

defineProps({
  budget: { type: Object, required: true },
  isFC: { type: Boolean, default: false },
})
</script>

<style scoped>
.budget-card {
  margin-top: 16px;
}
</style>
