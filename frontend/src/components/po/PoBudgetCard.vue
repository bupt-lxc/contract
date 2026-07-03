<template>
  <el-card class="budget-card">
    <template #header>
      <span>{{ $t('po.budgetSummary') }}</span>
    </template>
    <el-descriptions :column="3" border size="small">
      <!-- Row 1: always shown -->
      <el-descriptions-item :label="$t('po.poAmount')">
        <AmountDisplay :value="budget.po_amount" />
      </el-descriptions-item>
      <el-descriptions-item :label="$t('po.openPoAmount')">
        <AmountDisplay :value="budget.open_po_amount" />
      </el-descriptions-item>
      <el-descriptions-item label="" />

      <!-- FC-specific budget rows -->
      <template v-if="isFcPo">
        <el-descriptions-item :label="$t('po.allocatedCalloff')">
          <AmountDisplay :value="budget.allocated_calloff_amount" />
        </el-descriptions-item>
        <el-descriptions-item :label="$t('po.pendingCalloff')">
          <AmountDisplay :value="budget.pending_calloff_amount" />
        </el-descriptions-item>
        <el-descriptions-item :label="$t('po.downstreamConsumed')">
          <AmountDisplay :value="budget.downstream_consumed" />
        </el-descriptions-item>
        <el-descriptions-item :label="$t('po.downstreamPendingGr')">
          <AmountDisplay :value="budget.downstream_pending_gr" />
        </el-descriptions-item>
        <el-descriptions-item :label="$t('po.downstreamPendingGrIncl')">
          <AmountDisplay :value="budget.downstream_pending_gr_tax" />
        </el-descriptions-item>
        <el-descriptions-item label="" />
      </template>

      <!-- Regular PO budget rows -->
      <template v-else>
        <el-descriptions-item :label="$t('po.consumedAmount')">
          <AmountDisplay :value="budget.consumed_amount || budget.po_con_value_total" />
        </el-descriptions-item>
        <el-descriptions-item :label="$t('po.pendingExclTax')">
          <AmountDisplay :value="budget.pending_total || budget.po_pending_total" />
        </el-descriptions-item>
        <el-descriptions-item :label="$t('po.pendingInclTax')">
          <AmountDisplay :value="budget.pending_total_incl_tax || budget.po_pending_total_incl_tax" />
        </el-descriptions-item>
      </template>
    </el-descriptions>
  </el-card>
</template>

<script setup>
import AmountDisplay from '@/components/common/AmountDisplay.vue'

defineProps({
  budget: { type: Object, required: true },
  isFcPo: { type: Boolean, default: false }
})
</script>

<style scoped>
.budget-card {
  margin-top: 16px;
}
</style>
