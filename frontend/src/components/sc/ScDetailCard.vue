<template>
  <el-descriptions :column="2" border size="small" class="sc-descriptions">
    <el-descriptions-item label="SC ID">{{ sc.sc_id }}</el-descriptions-item>
    <el-descriptions-item label="SC No">{{ sc.sc_no || '-' }}</el-descriptions-item>
    <el-descriptions-item label="Requester">{{ sc.requester_id }}</el-descriptions-item>
    <el-descriptions-item label="Request Type">{{ sc.request_type }}</el-descriptions-item>
    <el-descriptions-item label="Cost Center">{{ sc.cost_center || '-' }}</el-descriptions-item>
    <el-descriptions-item label="SC Amount"><AmountDisplay :value="sc.sc_amount" /></el-descriptions-item>
    <el-descriptions-item label="Service Period Start">{{ formatDate(sc.service_period_start) }}</el-descriptions-item>
    <el-descriptions-item label="Service Period End">{{ formatDate(sc.service_period_end) }}</el-descriptions-item>
    <el-descriptions-item label="Description" :span="2">{{ sc.description || '-' }}</el-descriptions-item>
    <el-descriptions-item label="Created At">{{ formatDate(sc.created_at) }}</el-descriptions-item>
    <el-descriptions-item label="Updated At">{{ formatDate(sc.updated_at) }}</el-descriptions-item>
  </el-descriptions>
</template>

<script setup>
import AmountDisplay from '@/components/common/AmountDisplay.vue'

defineProps({
  sc: { type: Object, required: true }
})

function formatDate(val) {
  if (!val) return '-'
  return val.slice(0, 10)
}
</script>
