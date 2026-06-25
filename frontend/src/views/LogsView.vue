<template>
  <div>
    <AdvancedFilterBar
      :filter-config="logsFilterConfig"
      @filter="handleFilter"
      @reset="handleReset"
    />

    <div style="margin-bottom:12px">
      <el-button @click="handleExport" :loading="exporting">
        <el-icon><Download /></el-icon> {{ $t('common.export') }}
      </el-button>
    </div>

    <el-table :data="state.rows" v-loading="state.loading" stripe border>
      <el-table-column prop="created_at" :label="$t('record.created')" width="160" sortable="custom">
        <template #default="{ row }">{{ row.created_at?.slice(0,19) }}</template>
      </el-table-column>
      <el-table-column prop="action_type" :label="$t('record.action')" width="150" />
      <el-table-column prop="object_type" :label="$t('record.object')" width="100" />
      <el-table-column prop="object_id" :label="$t('record.objectId')" width="130" />
      <el-table-column prop="sc_id" :label="$t('record.scId')" width="130" />
      <el-table-column prop="operator_id" :label="$t('record.operator')" width="130" />
      <el-table-column prop="machine_id" :label="$t('record.machine')" min-width="130" />
      <template #empty><el-empty :description="state.error || $t('record.noRecords')" /></template>
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
import { onMounted, ref } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { useLogs } from '@/composables/useLogs.js'
import { useExport } from '@/composables/useExport.js'
import AdvancedFilterBar from '@/components/common/AdvancedFilterBar.vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'

const { state, searchLogs, setFilters, resetFilters, onPageChange, onPageSizeChange } = useLogs()
const { exportAll } = useExport()
const { t } = useI18n()
const exporting = ref(false)

const logsFilterConfig = [
  { name: 'action_type', label: t('record.action'), type: 'input' },
  { name: 'object_type', label: t('record.objectType'), type: 'input' },
  { name: 'object_id', label: t('record.objectId'), type: 'input' },
  { name: 'sc_id', label: t('record.scId'), type: 'input' },
  { name: 'operator_id', label: t('record.operator'), type: 'input' },
  { name: 'machine_id', label: t('record.machine'), type: 'input' },
  { name: 'operation_mode', label: t('record.mode'), type: 'input' },
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

async function handleExport() {
  exporting.value = true
  try {
    const columns = [
      { key: 'created_at', label: t('record.created'), getValue: r => (r.created_at || '').slice(0, 19) },
      { key: 'action_type', label: t('record.action') },
      { key: 'object_type', label: t('record.objectType') },
      { key: 'object_id', label: t('record.objectId') },
      { key: 'sc_id', label: t('record.scId') },
      { key: 'operator_id', label: t('record.operator') },
      { key: 'machine_id', label: t('record.machine') }
    ]
    await exportAll('search_operation_records', {
      filters: state.filters,
      sort: state.sort,
      direction: state.direction
    }, columns, `Operation_Records_${new Date().toISOString().slice(0, 10)}`)
    ElMessage.success(t('record.exportSuccess'))
  } catch (e) {
    ElMessage.error(e.message || t('record.exportFailed'))
  } finally {
    exporting.value = false
  }
}

onMounted(() => searchLogs())
</script>
