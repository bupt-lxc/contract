<template>
  <div>
    <AdvancedFilterBar
      :filter-config="vendorFilterConfig"
      @filter="handleFilter"
      @reset="handleReset"
    >
      <template #actions>
        <el-button type="primary" @click="dialogVisible = true; dialogMode = 'create'">
          <el-icon><Plus /></el-icon> {{ $t('vendor.addVendor') }}
        </el-button>
        <el-button @click="handleExport" :loading="exporting">
          <el-icon><Download /></el-icon> {{ $t('common.export') }}
        </el-button>
      </template>
    </AdvancedFilterBar>

    <el-table :data="state.rows" v-loading="state.loading" stripe border>
      <el-table-column prop="vendor_name" :label="$t('vendor.vendor')" sortable="custom" min-width="160" />
      <el-table-column prop="company_name_cn" :label="$t('vendor.companyNameCn')" min-width="140">
        <template #default="{ row }">{{ row.company_name_cn || '-' }}</template>
      </el-table-column>
      <el-table-column prop="ksrm_vendor_code" :label="$t('vendor.ksrmCode')" width="110" />
      <el-table-column prop="service_scope" :label="$t('vendor.serviceScope')" width="180" />
      <el-table-column prop="contact_person" :label="$t('vendor.contact')" width="110" />
      <el-table-column prop="phone" :label="$t('vendor.phone')" width="120" />
      <el-table-column prop="email" :label="$t('vendor.email')" min-width="160">
        <template #default="{ row }">{{ row.email || '-' }}</template>
      </el-table-column>
      <el-table-column :label="$t('common.actions')" width="140" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="dialogVisible = true; dialogMode = 'edit'; dialogRecord = row">{{ $t('common.edit') }}</el-button>
          <el-popconfirm :title="$t('vendor.disableConfirm')" @confirm="handleDisable(row)">
            <template #reference>
              <el-button type="danger" link size="small">{{ $t('common.disable') }}</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty><el-empty :description="state.error || $t('vendor.noRecords')" /></template>
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
import { useI18n } from 'vue-i18n'
import { Plus, Download } from '@element-plus/icons-vue'
import { useVendor } from '@/composables/useVendor.js'
import { useExport } from '@/composables/useExport.js'
import AdvancedFilterBar from '@/components/common/AdvancedFilterBar.vue'
import VendorFormDialog from '@/components/vendor/VendorFormDialog.vue'
import { ElMessage } from 'element-plus'

const { t } = useI18n()
const { state, searchVendors, createVendor, updateVendor, disableVendor } = useVendor()
const { exportRows } = useExport()
const exporting = ref(false)

const vendorFilterConfig = [
  { name: 'vendor_name', label: t('vendor.vendorName'), type: 'input' },
  { name: 'company_name_cn', label: t('vendor.companyNameCn'), type: 'input' },
  { name: 'vendor_id', label: t('vendor.vendorId'), type: 'input' },
  { name: 'ksrm_vendor_code', label: t('vendor.ksrmCode'), type: 'input' },
  { name: 'service_scope', label: t('vendor.serviceScope'), type: 'input' },
  { name: 'created_by', label: t('sc.createdBy'), type: 'input' },
  { name: 'contact_person', label: t('vendor.contact'), type: 'input' },
  { name: 'email', label: t('vendor.email'), type: 'input' },
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
      { key: 'vendor_name', label: t('vendor.vendorName') },
      { key: 'company_name_cn', label: t('vendor.companyNameCn') },
      { key: 'ksrm_vendor_code', label: t('vendor.ksrmCode') },
      { key: 'service_scope', label: t('vendor.serviceScope') },
      { key: 'contact_person', label: t('vendor.contact') },
      { key: 'phone', label: t('vendor.phone') },
      { key: 'email', label: t('vendor.email') }
    ]
    await exportRows(state.rows, columns, `Vendors_${new Date().toISOString().slice(0, 10)}`)
    ElMessage.success(t('export.exported'))
  } catch (e) {
    ElMessage.error(e.message || t('export.failed'))
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
    ElMessage.success(t('common.saved'))
    dialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
}

async function handleDisable(row) {
  try {
    await disableVendor(row.vendor_id)
    ElMessage.success(t('vendor.vendorDisabled'))
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(() => searchVendors())
</script>
