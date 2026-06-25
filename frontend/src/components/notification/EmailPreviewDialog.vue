<template>
  <el-dialog v-model="visible" title="Email Preview" width="750px" top="3vh" @closed="$emit('closed')">
    <div v-if="draft" style="max-height:70vh;overflow:auto">
      <div style="margin-bottom:12px;padding:8px 12px;background:#f5f5f5;border-radius:4px">
        <div style="margin-bottom:4px"><strong>Subject:</strong> {{ draft.subject }}</div>
        <div style="margin-bottom:4px"><strong>To:</strong> {{ (draft.to_addresses || []).join(', ') || 'None' }}</div>
        <div><strong>Cc:</strong> {{ (draft.cc_addresses || []).join(', ') || 'None' }}</div>
      </div>
      <div v-if="draft.attachments && draft.attachments.length" style="margin-bottom:12px">
        <strong>Attachments:</strong> {{ draft.attachments.join(', ') }}
      </div>
      <div v-html="draft.html_body" style="border:1px solid #ddd;padding:16px;max-height:400px;overflow:auto;background:#fff"></div>
    </div>
    <div v-else style="text-align:center;padding:40px">
      <el-icon class="spinner" :size="32"><Loading /></el-icon>
    </div>
    <template #footer>
      <el-button @click="visible = false">{{ $t('common.cancel') }}</el-button>
      <el-button type="primary" @click="openInOutlook" :loading="sending">{{ $t('email.openInOutlook') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { callApi } from '@/api/bridge.js'

const props = defineProps({
  modelValue: Boolean,
  entryId: [Number, String]
})
const emit = defineEmits(['update:modelValue', 'sent', 'closed'])
const visible = ref(false)
const draft = ref(null)
const sending = ref(false)

watch(() => props.modelValue, async (val) => {
  visible.value = val
  if (val && props.entryId) {
    draft.value = null
    draft.value = await callApi('generate_email_draft', { entry_id: props.entryId })
  }
})
watch(visible, (val) => {
  if (!val) emit('update:modelValue', false)
})

async function openInOutlook() {
  sending.value = true
  try {
    await callApi('open_email_draft_in_outlook', { entry_id: props.entryId })
    visible.value = false
    emit('sent')
  } finally {
    sending.value = false
  }
}
</script>
