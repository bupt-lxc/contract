<template>
  <el-dialog
    :model-value="visible"
    :title="$t('vendor.importVendors')"
    width="900px"
    top="5vh"
    @update:model-value="$emit('update:visible', $event)"
    @close="handleClose"
  >
    <!-- Step 1: File selection -->
    <div v-if="!preview" style="text-align:center;padding: 40px 0">
      <el-icon :size="48" style="color:#94a3b8"><Upload /></el-icon>
      <p style="margin:16px 0 8px;color:#475569">{{ $t('vendor.importHint') }}</p>
      <p style="color:#94a3b8;font-size:12px;margin-bottom:20px">{{ $t('vendor.importFormatHint') }}</p>
      <el-button type="primary" size="large" @click="handleSelectFile" :loading="loading">
        <el-icon><FolderOpened /></el-icon> {{ $t('vendor.selectFile') }}
      </el-button>
    </div>

    <!-- Step 2: Preview -->
    <div v-else>
      <div style="margin-bottom:12px;display:flex;align-items:center;gap:16px">
        <span style="font-size:13px;color:#475569">
          {{ $t('vendor.fileLabel') }}: <b>{{ fileName }}</b>
        </span>
        <el-tag size="small" type="success">{{ $t('vendor.validRows', { n: validCount }) }}</el-tag>
        <el-tag v-if="invalidCount > 0" size="small" type="danger">{{ $t('vendor.invalidRows', { n: invalidCount }) }}</el-tag>
      </div>

      <el-table :data="preview" max-height="400" stripe border size="small">
        <el-table-column type="index" width="45" />
        <el-table-column prop="vendor_id" :label="$t('vendor.vendorId')" width="120">
          <template #default="{ row }">
            <span :style="{ color: row._valid ? '' : '#f56c6c' }">{{ row.vendor_id || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="vendor_name" :label="$t('vendor.vendorName')" min-width="140">
          <template #default="{ row }">
            <span :style="{ color: row._valid ? '' : '#f56c6c' }">{{ row.vendor_name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="company_name_cn" :label="$t('vendor.companyNameCn')" min-width="120" />
        <el-table-column prop="service_scope" :label="$t('vendor.serviceScope')" width="140" />
        <el-table-column prop="contact_person" :label="$t('vendor.contact')" width="100" />
        <el-table-column prop="email" :label="$t('vendor.email')" min-width="150" />
        <el-table-column :label="$t('vendor.validation')" width="200">
          <template #default="{ row }">
            <div v-if="row._errors.length > 0" style="color:#f56c6c;font-size:12px">
              <span v-for="err in row._errors" :key="err">✗ {{ err }}<br /></span>
            </div>
            <div v-if="row._warnings && row._warnings.length > 0" style="color:#e6a23c;font-size:12px">
              <span v-for="w in row._warnings" :key="w">⚠ {{ w }}<br /></span>
            </div>
            <span v-if="row._valid && (!row._warnings || row._warnings.length === 0)" style="color:#67c23a">✓ {{ $t('vendor.valid') }}</span>
            <span v-else-if="row._valid && row._warnings && row._warnings.length > 0" style="color:#e6a23c">⚠ {{ $t('vendor.valid') }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="result" style="margin-top:16px">
        <el-alert
          :title="$t('vendor.importResult')"
          :type="result.imported > 0 ? 'success' : 'warning'"
          :closable="false"
        >
          <template #default>
            <span>{{ $t('vendor.imported', { n: result.imported }) }}</span>
            <span v-if="result.skipped > 0" style="margin-left:10px;color:#e6a23c">
              {{ $t('vendor.skippedRows', { n: result.skipped }) }}
            </span>
            <div v-if="result.errors.length > 0" style="margin-top:8px;max-height:120px;overflow-y:auto">
              <p v-for="(err, i) in result.errors" :key="i" style="font-size:12px;color:#909399;margin:2px 0">{{ err }}</p>
            </div>
          </template>
        </el-alert>
      </div>
    </div>

    <template #footer>
      <div v-if="preview && !result">
        <el-button @click="handleClose">{{ $t('common.cancel') }}</el-button>
        <el-button @click="handleReselect">{{ $t('vendor.reselect') }}</el-button>
        <el-button type="primary" @click="handleImport" :loading="importing" :disabled="validCount === 0">
          {{ $t('vendor.import') }} ({{ validCount }})
        </el-button>
      </div>
      <div v-else-if="result">
        <el-button type="primary" @click="handleDone">{{ $t('common.confirm') }}</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Upload, FolderOpened } from '@element-plus/icons-vue'
import { callApi } from '@/api/bridge.js'
import { ElMessage } from 'element-plus'

const { t } = useI18n()
const props = defineProps({
  visible: { type: Boolean, default: false }
})
const emit = defineEmits(['update:visible', 'imported'])

const loading = ref(false)
const importing = ref(false)
const preview = ref(null)
const filePath = ref('')
const result = ref(null)

const fileName = computed(() => {
  if (!filePath.value) return ''
  return filePath.value.split(/[/\\]/).pop()
})

const validCount = computed(() =>
  preview.value ? preview.value.filter(r => r._valid).length : 0
)

const invalidCount = computed(() =>
  preview.value ? preview.value.filter(r => !r._valid).length : 0
)

async function handleSelectFile() {
  loading.value = true
  try {
    const data = await callApi('preview_vendor_import')
    if (!data) {
      return // user cancelled file dialog
    }
    filePath.value = data.file_path
    preview.value = data.rows
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function handleImport() {
  importing.value = true
  try {
    const validRows = preview.value.filter(r => r._valid).map(r => {
      const { _errors, _valid, _warnings, ...rest } = r
      return rest
    })
    result.value = await callApi('confirm_vendor_import', { rows: validRows })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    importing.value = false
  }
}

function handleReselect() {
  preview.value = null
  filePath.value = ''
  result.value = null
}

function handleDone() {
  emit('imported')
  handleClose()
}

function handleClose() {
  preview.value = null
  filePath.value = ''
  result.value = null
  emit('update:visible', false)
}
</script>
