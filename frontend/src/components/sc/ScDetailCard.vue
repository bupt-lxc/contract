<template>
  <el-descriptions :column="2" border size="small" class="sc-descriptions">
    <el-descriptions-item :label="$t('sc.scId')">{{ sc.sc_id }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.scNo')">{{ sc.sc_no || '-' }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.requester')">{{ sc.requester_id }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.requestType')">{{ sc.request_type }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.costCenter')">{{ sc.cost_center || '-' }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.scAmount')"><AmountDisplay :value="sc.sc_amount" /></el-descriptions-item>
    <el-descriptions-item :label="$t('sc.servicePeriodStart')">{{ formatDate(sc.service_period_start) }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.servicePeriodEnd')">{{ formatDate(sc.service_period_end) }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.asset')">{{ sc.asset || '-' }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.assetNums')">{{ sc.asset_nums || '-' }}</el-descriptions-item>
    <el-descriptions-item v-if="sc.request_type === 'FC'" :label="$t('sc.internalSystemNumber')">{{ sc.internal_system_number || '-' }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.vendors')" :span="2">
      <template v-if="vendors && vendors.length">
        <el-collapse class="vendor-collapse">
          <el-collapse-item
            v-for="v in vendors"
            :key="v.vendor_id"
          >
            <template #title>
              <span class="vendor-title">{{ v.vendor_name }}</span>
              <el-tag size="small" type="info" style="margin-left:8px">{{ v.vendor_id }}</el-tag>
            </template>
            <div class="vendor-detail-grid">
              <div class="vendor-field">
                <span class="vendor-label">{{ $t('vendor.serviceScope') }}</span>
                <span>{{ v.service_scope || '-' }}</span>
              </div>
              <div class="vendor-field">
                <span class="vendor-label">{{ $t('vendor.contactPerson') }}</span>
                <span>{{ v.contact_person || '-' }}</span>
              </div>
              <div class="vendor-field">
                <span class="vendor-label">{{ $t('vendor.phone') }}</span>
                <span>{{ v.phone || '-' }}</span>
              </div>
              <div class="vendor-field">
                <span class="vendor-label">{{ $t('vendor.email') }}</span>
                <span>{{ v.email || '-' }}</span>
              </div>
              <div class="vendor-field" v-if="v.ksrm_vendor_code">
                <span class="vendor-label">{{ $t('vendor.ksrmCode') }}</span>
                <span>{{ v.ksrm_vendor_code }}</span>
              </div>
              <div class="vendor-field" v-if="v.description" style="grid-column:1/-1">
                <span class="vendor-label">{{ $t('vendor.description') }}</span>
                <span>{{ v.description }}</span>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </template>
      <span v-else>-</span>
    </el-descriptions-item>
    <el-descriptions-item :label="$t('sc.description')" :span="2">{{ sc.description || '-' }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.confirmedAt')">{{ formatDate(sc.confirmed_at) }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.pendingDate')">{{ formatDate(sc.pending_date) }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.approvedDate')">{{ formatDate(sc.approved_date) }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.createdAt')">{{ formatDate(sc.created_at) }}</el-descriptions-item>
    <el-descriptions-item :label="$t('sc.updatedAt')">{{ formatDate(sc.updated_at) }}</el-descriptions-item>
  </el-descriptions>
</template>

<script setup>
import AmountDisplay from '@/components/common/AmountDisplay.vue'

defineProps({
  sc: { type: Object, required: true },
  vendors: { type: Array, default: () => [] }
})

function formatDate(val) {
  if (!val) return '-'
  return val.slice(0, 10)
}
</script>

<style scoped>
.vendor-collapse {
  width: 100%;
}
.vendor-collapse :deep(.el-collapse-item__header) {
  height: auto;
  min-height: 36px;
  padding: 4px 0;
  border-bottom: none;
}
.vendor-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}
.vendor-collapse :deep(.el-collapse-item__content) {
  padding-bottom: 12px;
}
.vendor-title {
  font-weight: 600;
  font-size: 13px;
}
.vendor-detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 20px;
  padding: 4px 0;
}
.vendor-field {
  display: flex;
  flex-direction: column;
}
.vendor-label {
  font-size: 11px;
  color: #94a3b8;
  margin-bottom: 2px;
}
</style>
