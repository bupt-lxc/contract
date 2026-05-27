<template>
  <div>
    <FilterBar @reset="handleReset">
      <template #filters>
        <el-date-picker v-model="filters.created_at" type="date" placeholder="Date" value-format="YYYY-MM-DD" @change="onFilterChange" />
        <el-input v-model="filters.action_type" placeholder="Action type" clearable @change="onFilterChange" style="width:160px" />
      </template>
    </FilterBar>

    <el-table :data="filteredRows" v-loading="state.loading" stripe border>
      <el-table-column prop="created_at" label="Created" width="160" sortable="custom">
        <template #default="{ row }">{{ row.created_at?.slice(0,19) }}</template>
      </el-table-column>
      <el-table-column prop="action_type" label="Action" width="150" />
      <el-table-column prop="object_type" label="Object" width="100" />
      <el-table-column prop="object_id" label="Object ID" width="130" />
      <el-table-column prop="sc_id" label="SC ID" width="130" />
      <el-table-column prop="operator_id" label="Operator" width="130" />
      <el-table-column prop="machine_id" label="Machine" min-width="130" />
      <template #empty><el-empty :description="state.error || 'No audit logs found.'" /></template>
    </el-table>

    <el-pagination
      v-if="state.total > state.pageSize"
      :current-page="state.currentPage"
      :page-size="state.pageSize"
      :total="state.total"
      layout="total, sizes, prev, pager, next, jumper"
      @current-change="handlePageChange"
      @size-change="handleSizeChange"
      style="margin-top:12px;justify-content:flex-end"
    />
  </div>
</template>

<script setup>
import { reactive, computed, onMounted } from 'vue'
import { useLogs } from '@/composables/useLogs.js'
import FilterBar from '@/components/common/FilterBar.vue'

const { state, searchLogs, setFilters, resetFilters, onPageChange, onPageSizeChange } = useLogs()

const filters = reactive({ created_at: '', action_type: '' })

const filteredRows = computed(() => {
  let rows = state.rows
  if (filters.created_at) {
    rows = rows.filter(r => (r.created_at || '').startsWith(filters.created_at))
  }
  if (filters.action_type) {
    const t = filters.action_type.toLowerCase()
    rows = rows.filter(r => (r.action_type || '').toLowerCase().includes(t))
  }
  return rows
})

function onFilterChange() {
  const f = {}
  if (filters.action_type) f.action_type = filters.action_type
  setFilters(f)
  searchLogs(null, f)
}

function handleReset() {
  Object.assign(filters, { created_at: '', action_type: '' })
  resetFilters()
  searchLogs()
}

function handlePageChange(page) { onPageChange(page); searchLogs() }
function handleSizeChange(size) { onPageSizeChange(size); searchLogs() }

onMounted(() => searchLogs())
</script>
