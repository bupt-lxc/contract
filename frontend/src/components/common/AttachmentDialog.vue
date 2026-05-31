<template>
  <el-dialog
    :model-value="visible"
    :title="$t('attachment.attachments') + ' — ' + entityId"
    width="640px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <AttachmentList
      v-if="visible"
      :entity-type="entityType"
      :entity-id="entityId"
      :parent-sc-id="parentScId"
      :parent-po-id="parentPoId"
      @changed="$emit('changed')"
    />
    <template #footer>
      <el-button @click="$emit('update:visible', false)">{{ $t('common.cancel') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import AttachmentList from '@/components/common/AttachmentList.vue'

defineProps({
  visible: { type: Boolean, default: false },
  entityType: { type: String, required: true },
  entityId: { type: String, required: true },
  parentScId: { type: String, default: null },
  parentPoId: { type: String, default: null }
})

defineEmits(['update:visible', 'changed'])
</script>
