<template>
  <div class="filter-bar">
    <div class="filter-controls">
      <el-input
        v-model="searchText"
        placeholder="Search all fields..."
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
        {{ showAdvanced ? 'Hide' : 'Advanced' }} Filters
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
          v-model="filterValues[f.name]"
          :placeholder="f.label"
          clearable
          style="width: 160px"
          @change="emitFilters"
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
          v-model="filterValues[f.name]"
          :placeholder="f.label"
          clearable
          style="width: 160px"
          @change="emitFilters"
        />

        <!-- Date range filter -->
        <template v-else-if="f.type === 'date-range'">
          <el-date-picker
            v-model="filterValues[f.name + '_from']"
            :placeholder="f.label + ' from'"
            type="date"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 160px"
            @change="emitFilters"
          />
          <el-date-picker
            v-model="filterValues[f.name + '_to']"
            :placeholder="f.label + ' to'"
            type="date"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 160px"
            @change="emitFilters"
          />
        </template>

        <!-- Amount range filter -->
        <template v-else-if="f.type === 'amount-range'">
          <el-input-number
            v-model="filterValues[f.name + '_min']"
            :placeholder="f.label + ' min'"
            :precision="2"
            :min="0"
            controls-position="right"
            style="width: 160px"
            @change="emitFilters"
          />
          <el-input-number
            v-model="filterValues[f.name + '_max']"
            :placeholder="f.label + ' max'"
            :precision="2"
            :min="0"
            controls-position="right"
            style="width: 160px"
            @change="emitFilters"
          />
        </template>
      </template>

      <el-button @click="handleReset">Reset</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { Search } from '@element-plus/icons-vue'

const props = defineProps({
  filterConfig: { type: Array, default: () => [] }
})

const emit = defineEmits(['filter', 'reset'])

const searchText = ref('')
const showAdvanced = ref(false)
const filterValues = reactive({})

let debounceTimer = null

function onSearchDebounced() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    emitFilters()
  }, 500)
}

function emitFilters() {
  const filters = {}
  for (const [key, value] of Object.entries(filterValues)) {
    if (value !== null && value !== '' && value !== undefined) {
      filters[key] = value
    }
  }
  emit('filter', { text: searchText.value || null, filters })
}

function handleReset() {
  searchText.value = ''
  for (const key of Object.keys(filterValues)) {
    delete filterValues[key]
  }
  emit('reset')
}
</script>

<style scoped>
.filter-bar { padding: 12px 16px; background: #fff; border-radius: 4px; margin-bottom: 12px; }
.filter-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
.filter-actions { display: flex; gap: 8px; flex-shrink: 0; }
.advanced-filters { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding-top: 8px; border-top: 1px solid #e5e7eb; }
</style>
