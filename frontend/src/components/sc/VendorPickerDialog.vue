<template>
  <el-dialog
    :model-value="visible"
    :title="$t('sc.selectVendor')"
    width="640px"
    @update:model-value="$emit('update:visible', $event)"
    @closed="onClosed"
  >
    <el-input
      v-model="searchText"
      :placeholder="$t('common.search')"
      clearable
      style="margin-bottom:12px"
    >
      <template #prefix><el-icon><Search /></el-icon></template>
    </el-input>

    <el-table
      ref="tableRef"
      :data="filteredVendors"
      height="400"
      highlight-current-row
      @current-change="onCurrentChange"
      @row-dblclick="confirmPick"
    >
      <el-table-column prop="vendor_name" :label="$t('vendor.vendorName')" width="180" />
      <el-table-column prop="vendor_id" :label="$t('vendor.vendorId')" width="120" />
      <el-table-column prop="company_name_cn" :label="$t('vendor.companyNameCn')" min-width="140" />
      <el-table-column prop="service_scope" :label="$t('vendor.serviceScope')" width="140" />
      <el-table-column prop="contact_person" :label="$t('vendor.contact')" width="100" />
      <template #empty><el-empty :description="$t('vendor.noRecords')" /></template>
    </el-table>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">{{ $t('common.cancel') }}</el-button>
      <el-button type="primary" :disabled="!selected" @click="confirmPick">
        {{ $t('common.confirm') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Search } from '@element-plus/icons-vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  vendors: { type: Array, default: () => [] },
  excludeVendorIds: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:visible', 'pick'])

const tableRef = ref(null)
const searchText = ref('')
const selected = ref(null)

const filteredVendors = computed(() => {
  const exclude = new Set(props.excludeVendorIds)
  let list = props.vendors.filter(v => !exclude.has(v.vendor_id))
  if (searchText.value) {
    const q = searchText.value.toLowerCase()
    list = list.filter(v =>
      (v.vendor_name || '').toLowerCase().includes(q) ||
      (v.vendor_id || '').toLowerCase().includes(q) ||
      (v.company_name_cn || '').toLowerCase().includes(q)
    )
  }
  return list
})

function onCurrentChange(row) {
  selected.value = row ? row.vendor_id : null
}

function confirmPick() {
  if (selected.value) {
    emit('pick', selected.value)
    emit('update:visible', false)
  }
}

function onClosed() {
  searchText.value = ''
  selected.value = null
}
</script>
