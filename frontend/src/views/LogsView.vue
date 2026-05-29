<template>
  <div>
    <AdvancedFilterBar
      :filter-config="logsFilterConfig"
      @filter="handleFilter"
      @reset="handleReset"
    />

    <el-table :data="state.rows" v-loading="state.loading" stripe border>
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
import { onMounted } from 'vue'
import { useLogs } from '@/composables/useLogs.js'
import AdvancedFilterBar from '@/components/common/AdvancedFilterBar.vue'

const { state, searchLogs, setFilters, resetFilters, onPageChange, onPageSizeChange } = useLogs()

const logsFilterConfig = [
  { name: 'action_type', label: 'Action', type: 'input' },
  { name: 'object_type', label: 'Object Type', type: 'input' },
  { name: 'object_id', label: 'Object ID', type: 'input' },
  { name: 'sc_id', label: 'SC ID', type: 'input' },
  { name: 'operator_id', label: 'Operator', type: 'input' },
  { name: 'machine_id', label: 'Machine', type: 'input' },
  { name: 'operation_mode', label: 'Mode', type: 'input' },
]

function handleFilter({ text, filters }) {
  searchLogs(text, filters)
}

function handleReset() {
  resetFilters()
  searchLogs()
}

function handlePageChange(page) { onPageChange(page); searchLogs() }
function handleSizeChange(size) { onPageSizeChange(size); searchLogs() }

onMounted(() => searchLogs())
</script>
