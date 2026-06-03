<template>
  <el-dialog
    :model-value="visible"
    :title="title"
    width="420px"
    :close-on-click-modal="false"
    :show-close="false"
  >
    <div style="text-align:center;padding:12px 0">
      <p style="margin-bottom:8px;font-size:15px;color:#303133">
        {{ $t('batch.processing', { current: state.current, total: state.total }) }}
      </p>
      <p style="margin-bottom:16px;font-size:13px;color:#909399;font-family:monospace">
        {{ state.currentId }}
      </p>
      <div style="display:flex;justify-content:center;gap:24px;margin-bottom:16px">
        <span style="color:#67c23a;font-size:14px">
          {{ $t('batch.completed', { count: state.succeeded }) }}
        </span>
        <span style="color:#f56c6c;font-size:14px">
          {{ $t('batch.skipped', { count: state.failed + state.skipped }) }}
        </span>
      </div>
      <el-button type="danger" plain @click="$emit('abort')">
        {{ $t('batch.abort') }}
      </el-button>
    </div>
  </el-dialog>
</template>

<script setup>
defineProps({
  visible: { type: Boolean, default: false },
  title: { type: String, default: '' },
  state: { type: Object, required: true }
})

defineEmits(['abort'])
</script>
