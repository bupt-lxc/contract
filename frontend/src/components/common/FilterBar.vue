<template>
  <div class="filter-bar">
    <div class="filter-controls">
      <slot name="filters" />
      <el-button @click="$emit('reset')" :disabled="disabled">Reset</el-button>
    </div>
    <div class="filter-actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup>
defineProps({
  disabled: { type: Boolean, default: false }
})
defineEmits(['reset'])
</script>

<style scoped>
.filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #fff;
  border-radius: 4px;
  margin-bottom: 12px;
  gap: 12px;
}
.filter-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.filter-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
</style>
