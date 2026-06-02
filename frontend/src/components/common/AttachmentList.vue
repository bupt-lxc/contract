<template>
  <div>
    <div style="margin-bottom:12px">
      <el-button size="small" @click="handleAddFiles" :loading="uploading">
        <el-icon><Paperclip /></el-icon> {{ $t('attachment.addAttachment') }}
      </el-button>
      <el-button size="small" @click="handleOpenFolder">
        <el-icon><FolderOpened /></el-icon> {{ $t('attachment.openFolder') }}
      </el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="attachments"
      stripe
      border
      size="small"
      style="width:100%"
    >
      <el-table-column prop="filename" :label="$t('attachment.filename')" min-width="200" />
      <el-table-column :label="$t('attachment.fileSize')" width="100" align="right">
        <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
      </el-table-column>
      <el-table-column prop="created_by" :label="$t('attachment.uploadedBy')" width="120" />
      <el-table-column :label="$t('attachment.uploadedAt')" width="160">
        <template #default="{ row }">{{ row.created_at?.slice(0, 19) }}</template>
      </el-table-column>
      <el-table-column :label="$t('common.actions')" width="140" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="handleOpen(row)">{{ $t('attachment.openFile') }}</el-button>
          <el-popconfirm
            :title="$t('attachment.deleteConfirm')"
            :confirm-button-text="$t('common.confirm')"
            :cancel-button-text="$t('common.cancel')"
            @confirm="handleDelete(row)"
          >
            <template #reference>
              <el-button type="danger" link size="small">{{ $t('attachment.deleteAttachment') }}</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty :description="$t('attachment.noAttachments')" :image-size="60" />
      </template>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Paperclip, FolderOpened } from '@element-plus/icons-vue'
import { callApi } from '@/api/bridge.js'
import { ElMessage } from 'element-plus'

const props = defineProps({
  entityType: { type: String, required: true },
  entityId: { type: String, required: true },
  parentScId: { type: String, default: null },
  parentPoId: { type: String, default: null },
  refreshKey: { type: Number, default: 0 }
})

const emit = defineEmits(['changed'])

const { t } = useI18n()
const attachments = ref([])
const loading = ref(false)
const uploading = ref(false)

function formatSize(bytes) {
  if (bytes == null) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(1) + ' MB'
}

async function fetchAttachments() {
  loading.value = true
  try {
    attachments.value = await callApi('list_attachments', {
      entity_type: props.entityType,
      entity_id: props.entityId
    })
  } catch (e) {
    ElMessage.error(e.message)
    attachments.value = []
  } finally {
    loading.value = false
  }
}

async function handleAddFiles() {
  uploading.value = true
  try {
    const result = await callApi('select_files', {
      entity_type: props.entityType,
      entity_id: props.entityId,
      parent_sc_id: props.parentScId,
      parent_po_id: props.parentPoId,
    })
    if (result && result.length > 0) {
      ElMessage.success(t('attachment.addAttachment') + ' (' + result.length + ')')
      await fetchAttachments()
      emit('changed')
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    uploading.value = false
  }
}

async function handleOpenFolder() {
  try {
    await callApi('open_attachment_dir', {
      entity_type: props.entityType,
      entity_id: props.entityId,
      parent_sc_id: props.parentScId,
      parent_po_id: props.parentPoId,
    })
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function handleOpen(row) {
  try {
    await callApi('open_attachment', { id: row.id })
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function handleDelete(row) {
  try {
    await callApi('delete_attachment', { id: row.id })
    ElMessage.success(t('common.deleted'))
    await fetchAttachments()
    emit('changed')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(fetchAttachments)

// Re-fetch when switching entities or when parent triggers a refresh
watch([
  () => props.entityType,
  () => props.entityId,
  () => props.refreshKey,
], () => {
  fetchAttachments()
})
</script>
