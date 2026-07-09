<template>
  <span class="amount-display">
    <span v-if="currency && formatted !== '-'" class="amount-currency">{{ currencySymbol }}</span>
    {{ formatted }}
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  value: { type: [Number, String], default: null },
  currency: { type: String, default: null }
})

const { locale } = useI18n()

const currencySymbol = computed(() => {
  if (!props.currency) return ''
  const map = { CNY: '¥', USD: '$', EUR: '€' }
  return map[props.currency] || props.currency
})

const formatted = computed(() => {
  if (props.value == null || props.value === '') return '-'
  const num = Number(props.value)
  if (isNaN(num)) return String(props.value)
  return num.toLocaleString(locale.value === 'zh-CN' ? 'zh-CN' : 'en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
})
</script>

<style scoped>
.amount-display {
  font-variant-numeric: tabular-nums;
  text-align: right;
  display: inline-block;
}
.amount-currency {
  margin-right: 2px;
}
</style>
