<template>
  <el-dialog
    :model-value="visible"
    :close-on-click-modal="false"
    :show-close="false"
    :title="$t('update.newVersionAvailable')"
    width="480px"
    center
  >
    <p style="margin-bottom:12px">{{ $t('update.mustInstall', { version }) }}</p>
    <div v-if="changelog" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:12px;max-height:200px;overflow-y:auto;white-space:pre-wrap;font-size:13px;color:#475569">{{ changelog }}</div>

    <template #footer>
      <el-button
        type="primary"
        :loading="loading"
        @click="$emit('install')"
      >
        {{ $t('update.installNow') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
defineProps({
  visible: { type: Boolean, required: true },
  version: { type: String, default: '' },
  changelog: { type: String, default: '' },
  loading: { type: Boolean, default: false }
})

defineEmits(['install'])
</script>
