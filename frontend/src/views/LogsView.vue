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
      <el-table-column prop="created_at" :label="$t('audit.created')" width="160" sortable="custom">
        <template #default="{ row }">{{ row.created_at?.slice(0,19) }}</template>
      </el-table-column>
      <el-table-column prop="action_type" :label="$t('audit.action')" width="150" />
      <el-table-column prop="object_type" :label="$t('audit.object')" width="100" />
      <el-table-column prop="object_id" :label="$t('audit.objectId')" width="130" />
      <el-table-column prop="sc_id" :label="$t('audit.scId')" width="130" />
      <el-table-column prop="operator_id" :label="$t('audit.operator')" width="130" />
      <el-table-column prop="machine_id" :label="$t('audit.machine')" min-width="130" />
      <template #empty><el-empty :description="state.error || $t('audit.noRecords')" /></template>
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
  { name: 'action_type', label: t('audit.action'), type: 'input' },
  { name: 'object_type', label: t('audit.objectType'), type: 'input' },
  { name: 'object_id', label: t('audit.objectId'), type: 'input' },
  { name: 'sc_id', label: t('audit.scId'), type: 'input' },
  { name: 'operator_id', label: t('audit.operator'), type: 'input' },
  { name: 'machine_id', label: t('audit.machine'), type: 'input' },
  { name: 'operation_mode', label: t('audit.mode'), type: 'input' },
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
      { key: 'created_at', label: t('audit.created'), getValue: r => (r.created_at || '').slice(0, 19) },
      { key: 'action_type', label: t('audit.action') },
      { key: 'object_type', label: t('audit.objectType') },
      { key: 'object_id', label: t('audit.objectId') },
      { key: 'sc_id', label: t('audit.scId') },
      { key: 'operator_id', label: t('audit.operator') },
      { key: 'machine_id', label: t('audit.machine') }
    ]
    await exportAll('search_audit_logs', {
      filters: state.filters,
      sort: state.sort,
      direction: state.direction
    }, columns, `Audit_Logs_${new Date().toISOString().slice(0, 10)}`)
    ElMessage.success(t('audit.exportSuccess'))
  } catch (e) {
    ElMessage.error(e.message || t('audit.exportFailed'))
  } finally {
    exporting.value = false
  }
}

onMounted(() => searchLogs())
</script>
