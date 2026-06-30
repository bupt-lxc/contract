<template>
  <el-descriptions :column="2" border size="small" class="sc-descriptions">
    <el-descriptions-item :label="$t('sc.scId')">{{ sc.sc_id }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.scNo')">{{ sc.sc_no || '-' }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.requester')">{{ sc.requester_name || sc.requester_id }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.requestType')">{{ sc.request_type }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.costCenter')">{{ sc.cost_center || '-' }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.scAmount')"><AmountDisplay :value="sc.sc_amount" /></el-descriptions-item>
    <el-descriptions-item :label="$t('sc.currency')">{{ sc.currency || 'CNY' }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.servicePeriodStart')">{{ formatDate(sc.service_period_start) }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.servicePeriodEnd')">{{ formatDate(sc.service_period_end) }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.asset')">{{ sc.asset || '-' }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.assetNums')">{{ sc.asset_nums || '-' }}</el-descriptions-item>
    <el-descriptions-item v-if="sc.request_type === 'FC'" :label="$t('sc.internalSystemNumber')">{{ sc.internal_system_number || '-' }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.description')" :span="2">{{ sc.description || '-' }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.confirmedAt')">{{ formatDate(sc.confirmed_at) }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.createdAt')">{{ formatDate(sc.created_at) }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.submittedDate')">{{ formatDate(sc.submitted_date) }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.pendingDate')">{{ formatDate(sc.pending_date) }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.approvedDate')">{{ formatDate(sc.approved_date) }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.updatedAt')">{{ formatDate(sc.updated_at) }}</el-descriptions-item>
  </el-descriptions>
</template>

<script setup>
import AmountDisplay from '@/components/common/AmountDisplay.vue'

defineProps({
  sc: { type: Object, required: true }
})

function formatDate(val) {
  if (!val) return '-'
  return val.slice(0, 10)
}
</script>

