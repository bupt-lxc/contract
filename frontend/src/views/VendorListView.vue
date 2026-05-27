<template>
  <div>
    <FilterBar @reset="handleReset">
      <template #filters>
        <el-select v-model="filters.service_scope" placeholder="Service Scope" clearable @change="onFilterChange">
          <el-option v-for="s in serviceScopes" :key="s" :label="s" :value="s" />
        </el-select>
        <el-input v-model="filters.text" placeholder="Vendor name / KSRM code" clearable @change="onFilterChange" style="width:220px" />
      </template>
      <template #actions>
        <el-button type="primary" @click="dialogVisible = true; dialogMode = 'create'">
          <el-icon><Plus /></el-icon> Add Vendor
        </el-button>
      </template>
    </FilterBar>

    <el-table :data="filteredRows" v-loading="state.loading" stripe border>
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
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { useVendor } from '@/composables/useVendor.js'
import FilterBar from '@/components/common/FilterBar.vue'
import VendorFormDialog from '@/components/vendor/VendorFormDialog.vue'
import { ElMessage } from 'element-plus'

const { state, searchVendors, createVendor, updateVendor, disableVendor } = useVendor()

const serviceScopes = [
  'Transportation', 'engineering Service', 'Equipment', 'Parts', 'Driver',
  'Test car rental', 'General Service', 'Dealers', 'Import&Export&cusoms clearance',
  'Insurance', 'Harness', 'Maintenance', 'Security', 'Testing support', 'Others'
]

const filters = reactive({ service_scope: '', text: '' })
const dialogVisible = ref(false)
const dialogMode = ref('create')
const dialogRecord = ref(null)

const filteredRows = computed(() => {
  let rows = state.rows
  if (filters.service_scope) {
    rows = rows.filter(r => r.service_scope === filters.service_scope)
  }
  if (filters.text) {
    const t = filters.text.toLowerCase()
    rows = rows.filter(r =>
      (r.vendor_name || '').toLowerCase().includes(t) ||
      (r.ksrm_vendor_code || '').toLowerCase().includes(t)
    )
  }
  return rows
})

function onFilterChange() { /* client-side filters, no server re-fetch needed */ }
function handleReset() { Object.assign(filters, { service_scope: '', text: '' }) }

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
