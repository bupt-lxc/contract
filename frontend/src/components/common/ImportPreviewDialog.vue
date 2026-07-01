<template>
  <el-dialog
    :model-value="visible"
    :title="$t('common.importRecords', { entity: entityType })"
    width="1000px"
    top="3vh"
    @close="handleClose"
  >
    <!-- Step 1: File selection -->
    <div v-if="!preview" style="text-align:center;padding:20px 0">
      <el-alert type="info" :closable="false" style="margin-bottom:20px;text-align:left">
        {{ rulesText }}
      </el-alert>

      <el-button type="primary" plain @click="handleDownloadTemplate" style="margin-bottom:16px">
        <el-icon><Download /></el-icon> {{ $t('common.template') }}
      </el-button>

      <el-upload
        :auto-upload="false"
        :on-change="handleFileSelect"
        :limit="1"
        accept=".xlsx,.xls"
        drag
      >
        <el-icon :size="40"><UploadFilled /></el-icon>
        <div style="margin-top:8px">{{ $t('common.importDropHint') }}</div>
        <template #tip>
          <div style="margin-top:8px">{{ $t('common.importFormatHint') }}</div>
        </template>
      </el-upload>
    </div>

    <!-- Step 2: Preview -->
    <div v-else>
      <div style="margin-bottom:12px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <span style="font-size:13px;color:#475569">
          {{ $t('common.importFile') }}: <b>{{ fileName }}</b>
        </span>
        <el-tag size="small" type="success">{{ $t('common.importValid', { n: validCount }) }}</el-tag>
        <el-tag v-if="invalidCount > 0" size="small" type="danger">{{ $t('common.importInvalid', { n: invalidCount }) }}</el-tag>
        <el-tag size="small" type="info">{{ $t('common.importSelected', { n: selectedCount }) }}</el-tag>
      </div>

      <el-table
        ref="tableRef"
        :data="preview"
        max-height="420"
        stripe
        border
        size="small"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="40" :selectable="rowSelectable" />
        <el-table-column type="index" width="45" :label="'#'" />
        <el-table-column
          v-for="col in columns"
          :key="col.prop"
          :prop="col.prop"
          :label="col.label"
          :width="col.width"
          :min-width="col.minWidth"
        >
          <template #default="{ row }">
            <span :style="{ color: row._valid ? '' : '#c0c4cc' }">{{ row[col.prop] || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.importValidation')" width="200">
          <template #default="{ row }">
            <div v-if="row._errors && row._errors.length > 0" style="color:#f56c6c;font-size:12px">
              <span v-for="err in row._errors" :key="err" style="display:block">&#10007; {{ err }}</span>
            </div>
            <span v-else style="color:#67c23a">&#10003; Valid</span>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="importResult" style="margin-top:16px">
        <el-alert
          v-if="importResult.ok"
          type="success"
          :closable="false"
        >
          <template #title>
            Imported {{ importResult.count }} records
            <span v-if="importResult.skipped_duplicate > 0">({{ importResult.skipped_duplicate }} duplicates skipped)</span>
          </template>
        </el-alert>
        <el-alert v-else type="error" :closable="false">
          <template #title>
            <div v-for="e in importResult.errors" :key="e.row">Row {{ e.row }}: {{ e.field }} - {{ e.message }}</div>
          </template>
        </el-alert>
      </div>
    </div>

    <template #footer>
      <div v-if="!preview">
        <el-button @click="handleClose">{{ $t('common.cancel') }}</el-button>
      </div>
      <div v-else-if="!importResult">
        <el-button @click="handleClose">{{ $t('common.cancel') }}</el-button>
        <el-button @click="handleReselect">{{ $t('common.importReSelect') }}</el-button>
        <el-button type="primary" @click="handleImport" :loading="importing" :disabled="selectedCount === 0">
          {{ $t('common.importConfirm', { n: selectedCount }) }}
        </el-button>
      </div>
      <div v-else>
        <el-button type="primary" @click="handleDone">{{ $t('common.confirm') }}</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, nextTick, watch } from 'vue'
import { Download, UploadFilled } from '@element-plus/icons-vue'
import { callApi } from '@/api/bridge.js'
import { ElMessage } from 'element-plus'
import * as XLSX from 'xlsx'

const props = defineProps({
  visible: { type: Boolean, default: false },
  entityType: { type: String, required: true },
  columns: { type: Array, required: true },
  rulesText: { type: String, default: '' },
})

const emit = defineEmits(['update:visible', 'imported'])

const loading = ref(false)
const importing = ref(false)
const preview = ref(null)
const fileName = ref('')
const importResult = ref(null)
const tableRef = ref(null)
const selectedRows = ref([])

const validCount = computed(() =>
  preview.value ? preview.value.filter(r => r._valid).length : 0
)
const invalidCount = computed(() =>
  preview.value ? preview.value.filter(r => !r._valid).length : 0
)
const selectedCount = computed(() => selectedRows.value.length)

function rowSelectable(row) {
  return row._valid === true
}

function handleSelectionChange(selection) {
  selectedRows.value = selection
}

async function handleDownloadTemplate() {
  try {
    const entity = props.entityType.toLowerCase()
    const result = await callApi(`download_${entity}_template`)
    const saveResult = await callApi('save_file', { filename: result.filename, data: result.data })
    if (saveResult?.cancelled) return
    ElMessage.success('Template downloaded')
  } catch (e) {
    ElMessage.error(e.message || 'Failed to download template')
  }
}

async function handleFileSelect(uploadFile) {
  const file = uploadFile.raw
  if (!file) {
    ElMessage.error('No file selected')
    return
  }
  loading.value = true
  fileName.value = file.name
  try {
    const data = await file.arrayBuffer()
    const wb = XLSX.read(data, { type: 'array' })
    const ws = wb.Sheets[wb.SheetNames[0]]
    const rows = XLSX.utils.sheet_to_json(ws, { defval: '' })
    const entity = props.entityType.toLowerCase()
    const result = await callApi(`preview_${entity}_import`, { rows })
    preview.value = result.rows
    await nextTick()
    if (tableRef.value) {
      preview.value.forEach((row) => {
        if (row._valid) {
          tableRef.value.toggleRowSelection(row, true)
        }
      })
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function handleImport() {
  importing.value = true
  try {
    const cleanRows = selectedRows.value.map(r => {
      const { _errors, _valid, ...rest } = r
      return rest
    })
    const entity = props.entityType.toLowerCase()
    const importMethod = `import_${entity}s`
    importResult.value = await callApi(importMethod, { rows: cleanRows })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    importing.value = false
  }
}

function handleReselect() {
  preview.value = null
  fileName.value = ''
  importResult.value = null
  selectedRows.value = []
}

function handleDone() {
  emit('imported')
  handleClose()
}

function handleClose() {
  preview.value = null
  fileName.value = ''
  importResult.value = null
  selectedRows.value = []
  emit('update:visible', false)
}

watch(() => props.visible, (newVal) => {
  if (!newVal) {
    preview.value = null
    fileName.value = ''
    importResult.value = null
    selectedRows.value = []
  }
})
</script>
