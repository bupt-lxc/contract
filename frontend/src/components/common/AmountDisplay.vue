<template>
  <span class="amount-display">{{ formatted }}</span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  value: { type: [Number, String], default: null }
})

const formatted = computed(() => {
  if (props.value == null || props.value === '') return '-'
  const num = Number(props.value)
  if (isNaN(num)) return String(props.value)
  return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
})
</script>

<style scoped>
.amount-display {
  font-variant-numeric: tabular-nums;
  text-align: right;
  display: inline-block;
}
</style>
