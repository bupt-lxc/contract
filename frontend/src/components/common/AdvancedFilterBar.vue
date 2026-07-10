<template>
  <div class="filter-bar">
    <div class="filter-controls">
      <el-input
        v-model="searchText"
        :placeholder="$t('common.search')"
        :prefix-icon="Search"
        clearable
        style="width: 260px"
        @input="onSearchDebounced"
      />
      <el-button
        text
        type="primary"
        @click="showAdvanced = !showAdvanced"
      >
        {{ showAdvanced ? $t('common.hide') + ' ' + $t('common.filters') : $t('common.advanced') + ' ' + $t('common.filters') }}
      </el-button>
    </div>
    <div class="filter-actions">
      <slot name="actions" />
    </div>

    <div v-if="showAdvanced" class="advanced-filters">
      <template v-for="f in filterConfig" :key="f.name">
        <!-- Select filter -->
        <el-select
          v-if="f.type === 'select'"
          :model-value="filters[f.name]"
          :placeholder="f.label"
          clearable
          style="width: 160px"
          @update:model-value="value => updateFilter(f.name, value)"
        >
          <el-option
            v-for="opt in f.options"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>

        <!-- Input filter -->
        <el-input
          v-else-if="f.type === 'input'"
          :model-value="filters[f.name]"
          :placeholder="f.label"
          clearable
          style="width: 160px"
          @update:model-value="value => updateFilter(f.name, value)"
        />

        <!-- Date range filter -->
        <template v-else-if="f.type === 'date-range'">
          <el-date-picker
            :model-value="filters[f.name + '_from']"
            :placeholder="f.label + ' ' + $t('common.from')"
            type="date"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 160px"
            @update:model-value="value => updateFilter(f.name + '_from', value)"
          />
          <el-date-picker
            :model-value="filters[f.name + '_to']"
            :placeholder="f.label + ' ' + $t('common.to')"
            type="date"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 160px"
            @update:model-value="value => updateFilter(f.name + '_to', value)"
          />
        </template>

        <!-- Amount range filter -->
        <template v-else-if="f.type === 'amount-range'">
          <el-input-number
            :model-value="filters[f.name + '_min']"
            :placeholder="f.label + ' ' + $t('common.min')"
            :precision="2"
            :min="0"
            controls-position="right"
            style="width: 160px"
            @update:model-value="value => updateFilter(f.name + '_min', value)"
          />
          <el-input-number
            :model-value="filters[f.name + '_max']"
            :placeholder="f.label + ' ' + $t('common.max')"
            :precision="2"
            :min="0"
            controls-position="right"
            style="width: 160px"
            @update:model-value="value => updateFilter(f.name + '_max', value)"
          />
        </template>
      </template>

      <el-button @click="handleReset">{{ $t('common.reset') }}</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { Search } from '@element-plus/icons-vue'

const props = defineProps({
  filterConfig: { type: Array, default: () => [] },
  text: { type: String, default: '' },
  filters: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['update:text', 'update:filters', 'filter', 'reset'])

const searchText = computed({
  get: () => props.text || '',
  set: value => emit('update:text', value),
})

const showAdvanced = ref(false)
let debounceTimer = null
let pendingText = props.text || ''

watch(
  () => props.filters,
  value => {
    if (Object.keys(value || {}).length) showAdvanced.value = true
  },
  { immediate: true, deep: true },
)

watch(
  () => props.text,
  value => { pendingText = value || '' },
)

onUnmounted(() => clearTimeout(debounceTimer))

function emitFilterPayload(text = props.text || '') {
  emit('filter', { text: text || null, filters: props.filters || {} })
}

function updateFilter(key, value) {
  const next = { ...(props.filters || {}) }
  if (value === null || value === '' || value === undefined) delete next[key]
  else next[key] = value
  emit('update:filters', next)
  emit('filter', { text: pendingText || props.text || null, filters: next })
}

function onSearchDebounced(value) {
  pendingText = value || ''
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => emitFilterPayload(pendingText), 500)
}

function handleReset() {
  clearTimeout(debounceTimer)
  pendingText = ''
  emit('update:text', '')
  emit('update:filters', {})
  emit('reset')
}
</script>

<style scoped>
.filter-bar { padding: 12px 16px; background: #fff; border-radius: 4px; margin-bottom: 12px; }
.filter-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
.filter-actions { display: flex; gap: 8px; flex-shrink: 0; }
.advanced-filters { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding-top: 8px; border-top: 1px solid #e5e7eb; }
</style>
