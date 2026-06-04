<template>
  <div>
    <div class="section-header">
      <h3>{{ $t('sc.vendors') }}</h3>
      <el-button v-if="canManage" type="primary" size="small" @click="pickerVisible = true">
        <el-icon><Plus /></el-icon> {{ $t('sc.addVendor') }}
      </el-button>
    </div>

    <el-empty v-if="!vendors.length" :description="$t('sc.noVendors')" />

    <div v-else class="vendor-list">
      <div v-for="v in vendors" :key="v.vendor_id" class="vendor-row">
        <el-collapse class="vendor-collapse">
          <el-collapse-item>
            <template #title>
              <span class="vendor-title">{{ v.vendor_name }}</span>
              <el-tag size="small" type="info" style="margin-left:8px">{{ v.vendor_id }}</el-tag>
            </template>
            <div class="vendor-detail-grid">
              <div class="vendor-field" v-if="v.company_name_cn">
                <span class="vendor-label">{{ $t('vendor.companyNameCn') }}</span>
                <span>{{ v.company_name_cn }}</span>
              </div>
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

        <el-popconfirm
          v-if="canManage"
          :title="$t('sc.confirmRemoveVendor', { name: v.vendor_name })"
          @confirm="$emit('remove', v.vendor_id)"
        >
          <template #reference>
            <el-button type="danger" link size="small" style="margin-left:8px;flex-shrink:0">
              <el-icon><Delete /></el-icon>
            </el-button>
          </template>
        </el-popconfirm>
      </div>
    </div>

    <VendorPickerDialog
      v-model:visible="pickerVisible"
      :vendors="allVendors"
      :exclude-vendor-ids="existingVendorIds"
      @pick="vendorId => $emit('add', vendorId)"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import VendorPickerDialog from './VendorPickerDialog.vue'

const props = defineProps({
  vendors: { type: Array, default: () => [] },
  allVendors: { type: Array, default: () => [] },
  canManage: { type: Boolean, default: false }
})

defineEmits(['add', 'remove'])

const pickerVisible = ref(false)

const existingVendorIds = computed(() => props.vendors.map(v => v.vendor_id))
</script>

<style scoped>
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.section-header h3 {
  font-size: 15px;
  font-weight: 600;
}
.vendor-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.vendor-row {
  display: flex;
  align-items: flex-start;
}
.vendor-collapse {
  flex: 1;
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
