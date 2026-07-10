<template>
  <el-descriptions :column="2" border size="small" class="sc-descriptions">
    <el-descriptions-item :label="$t('sc.scId')">{{ sc.sc_id }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.scNo')">{{ sc.sc_no || '-' }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.requester')">{{ sc.requester_name || sc.requester_id }}</el-descriptions-item>
    <el-descriptions-item v-if="sc.assignees && sc.assignees.length" :label="$t('sc.assignees')">
      {{ sc.assignees.map(a => a.user_name).join(', ') }}
    </el-descriptions-item>
    <el-descriptions-item :label="$t('sc.requestType')">{{ sc.request_type }}</el-descriptions-item>
    <el-descriptions-item v-if="sc.service_scope" :label="$t('vendor.serviceScope')">
      {{ sc.service_scope }}
    </el-descriptions-item>
    <el-descriptions-item :label="$t('sc.costCenter')">{{ sc.cost_center || '-' }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.scAmount')"><AmountDisplay :value="sc.sc_amount" /></el-descriptions-item>
    <el-descriptions-item :label="$t('sc.currency')">{{ sc.currency || 'CNY' }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.servicePeriodStart')">{{ formatDate(sc.service_period_start) }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.servicePeriodEnd')">{{ formatDate(sc.service_period_end) }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.asset')">{{ sc.asset || '-' }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.assetNums')">{{ sc.asset_nums || '-' }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.internalSystemNumber')">
      <el-button v-if="sc.calloff_po_id && sc.internal_system_number" type="primary" link size="small" @click="$router.push({ name: 'po-detail-independent', params: { poId: sc.calloff_po_id } })">
        {{ sc.internal_system_number }}
      </el-button>
      <span v-else>{{ sc.internal_system_number || '-' }}</span>
    </el-descriptions-item>
    <el-descriptions-item :label="$t('sc.description')" :span="2">{{ sc.description || '-' }}</el-descriptions-item>
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

