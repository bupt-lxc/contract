<template>
  <div>
    <AdvancedFilterBar
      :filter-config="vendorFilterConfig"
      @filter="handleFilter"
      @reset="handleReset"
    >
      <template #actions>
        <el-button type="primary" @click="dialogVisible = true; dialogMode = 'create'">
          <el-icon><Plus /></el-icon> Add Vendor
        </el-button>
        <el-button @click="handleExport" :loading="exporting">
          <el-icon><Download /></el-icon> Export
        </el-button>
      </template>
    </AdvancedFilterBar>

    <el-table :data="state.rows" v-loading="state.loading" stripe border>
      <el-table-column prop="vendor_name" label="Vendor" sortable="custom" min-width="160" />
      <el-table-column prop="ksrm_vendor_code" label="KSRM Code" width="110" />
      <el-table-column prop="service_scope" label="Service Scope" width="180" />
      <el-table-column prop="contact_person" label="Contact" width="110" />
      <el-table-column prop="phone" label="Phone" width="120" />
      <el-table-column prop="email" label="Email" min-width="160">
        <template #default="{ row }">{{ row.email || '-' }}</template>
      </el-table-column>
      <el-table-column label="Actions" width="140" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="dialogVisible = true; dialogMode = 'edit'; dialogRecord = row">Edit</el-button>
          <el-popconfirm title="Disable this vendor?" @confirm="handleDisable(row)">
            <template #reference>
              <el-button type="danger" link size="small">Disable</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty><el-empty :description="state.error || 'No vendors found.'" /></template>
    </el-table>

    <VendorFormDialog
      v-model:visible="dialogVisible"
      :mode="dialogMode"
      :record="dialogRecord"
      @save="handleSave"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Plus, Download } from '@element-plus/icons-vue'
import { useVendor } from '@/composables/useVendor.js'
import { useExport } from '@/composables/useExport.js'
import AdvancedFilterBar from '@/components/common/AdvancedFilterBar.vue'
import VendorFormDialog from '@/components/vendor/VendorFormDialog.vue'
import { ElMessage } from 'element-plus'

const { state, searchVendors, createVendor, updateVendor, disableVendor } = useVendor()
const { exportRows } = useExport()
const exporting = ref(false)

const vendorFilterConfig = [
  { name: 'vendor_name', label: 'Vendor Name', type: 'input' },
  { name: 'vendor_id', label: 'Vendor ID', type: 'input' },
  { name: 'ksrm_vendor_code', label: 'KSRM Code', type: 'input' },
  { name: 'service_scope', label: 'Service Scope', type: 'input' },
  { name: 'created_by', label: 'Created By', type: 'input' },
  { name: 'contact_person', label: 'Contact', type: 'input' },
  { name: 'email', label: 'Email', type: 'input' },
]

const dialogVisible = ref(false)
const dialogMode = ref('create')
const dialogRecord = ref(null)

function handleFilter({ text, filters }) {
  searchVendors(text, filters)
}

function handleReset() {
  searchVendors()
}

async function handleExport() {
  exporting.value = true
  try {
    const columns = [
      { key: 'vendor_name', label: 'Vendor Name' },
      { key: 'ksrm_vendor_code', label: 'KSRM Code' },
      { key: 'service_scope', label: 'Service Scope' },
      { key: 'contact_person', label: 'Contact' },
      { key: 'phone', label: 'Phone' },
      { key: 'email', label: 'Email' }
    ]
    await exportRows(state.rows, columns, `Vendors_${new Date().toISOString().slice(0, 10)}`)
    ElMessage.success('Exported successfully')
  } catch (e) {
    ElMessage.error(e.message || 'Export failed')
  } finally {
    exporting.value = false
  }
}

async function handleSave(data) {
  try {
    if (dialogMode.value === 'create') {
      await createVendor(data)
    } else {
      await updateVendor(data.vendor_id, data)
    }
    dialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
}

async function handleDisable(row) {
  try {
    await disableVendor(row.vendor_id)
    ElMessage.success('Vendor disabled')
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(() => searchVendors())
</script>
