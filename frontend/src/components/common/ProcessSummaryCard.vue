<template>
  <el-card class="process-summary-card" shadow="hover">
    <template #header>
      <span>{{ $t('processSummary') }}</span>
    </template>
    <el-descriptions :column="2" border size="small">
      <el-descriptions-item
        v-for="field in fields"
        :key="field.key"
        :label="field.label"
      >
        <span v-if="record[field.key]">{{ (record[field.key] || '').slice(0, 10) || '-' }}</span>
        <span v-else>-</span>
      </el-descriptions-item>
    </el-descriptions>
  </el-card>
</template>

<script setup>
defineProps({
  record: { type: Object, required: true },
  fields: { type: Array, required: true },
})
</script>

<style scoped>
.process-summary-card {
  margin-top: 16px;
}
</style>
