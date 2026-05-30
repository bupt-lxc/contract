<template>
  <div>
    <AdvancedFilterBar
      :filter-config="scFilterConfig"
      @filter="handleFilter"
      @reset="handleReset"
    >
      <template #actions>
        <el-button type="primary" @click="scDialogVisible = true; scDialogMode = 'create'">
          <el-icon><Plus /></el-icon> {{ $t('sc.newSc') }}
        </el-button>
        <el-button @click="handleExport" :loading="exporting">
          <el-icon><Download /></el-icon> {{ $t('common.export') }}
        </el-button>
      </template>
    </AdvancedFilterBar>

    <ScTable
      :rows="state.rows"
      :loading="state.loading"
      :empty-text="state.error || $t('sc.noRecords')"
      @sort-change="handleSortChange"
      @row-click="row => $router.push(`/sc/${row.sc_id}`)"
    />

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

    <ScFormDialog
      v-model:visible="scDialogVisible"
      :mode="scDialogMode"
      :record="scDialogRecord"
      :users="activeUsers"
      @save-draft="handleSaveDraft"
      @save-submit="handleSaveSubmit"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Plus, Download } from '@element-plus/icons-vue'
import { useSc } from '@/composables/useSc.js'
import { useExport } from '@/composables/useExport.js'
import { callApi } from '@/api/bridge.js'
import AdvancedFilterBar from '@/components/common/AdvancedFilterBar.vue'
import ScTable from '@/components/sc/ScTable.vue'
import ScFormDialog from '@/components/sc/ScFormDialog.vue'
import { ElMessage } from 'element-plus'

const { state, searchScs, createDraft, submitSc, setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange } = useSc()
const { exportAll } = useExport()
const { t } = useI18n()
const exporting = ref(false)

const scStatuses = [
  { label: t('status.pending'), value: 'pending' }, { label: t('status.approved'), value: 'approved' },
  { label: t('status.denied'), value: 'denied' }, { label: t('status.closed'), value: 'closed' }
]
const requestTypes = ['material', 'service', 'fixed_asset', 'FC']
const activeUsers = ref([])

const scFilterConfig = [
  { name: 'status', label: t('filter.status'), type: 'select', options: scStatuses },
  { name: 'request_type', label: t('filter.requestType'), type: 'select', options: requestTypes.map(t => ({ label: t, value: t })) },
  { name: 'cost_center', label: t('filter.costCenter'), type: 'input' },
  { name: 'sc_id', label: t('filter.scId'), type: 'input' },
  { name: 'sc_no', label: t('filter.scNo'), type: 'input' },
  { name: 'requester_id', label: t('filter.requesterId'), type: 'input' },
  { name: 'requester_name', label: t('filter.requesterName'), type: 'input' },
  { name: 'created_by', label: t('filter.createdById'), type: 'input' },
  { name: 'created_by_name', label: t('filter.createdByName'), type: 'input' },
  { name: 'service_period_start', label: t('filter.serviceStart'), type: 'date-range' },
  { name: 'sc_amount', label: t('filter.scAmount'), type: 'amount-range' },
]

const scDialogVisible = ref(false)
const scDialogMode = ref('create')
const scDialogRecord = ref(null)

function handleFilter({ text, filters }) {
  searchScs(text, filters)
}

function handleReset() {
  resetFilters()
  searchScs()
}

function handleSortChange({ prop, order }) {
  onSortChange({ prop, order })
  searchScs()
}

function handlePageChange(page) { onPageChange(page); searchScs() }
function handleSizeChange(size) { onPageSizeChange(size); searchScs() }

async function handleSaveDraft(data) {
  try {
    const { _attachments, ...formData } = data
    const created = await createDraft(formData)
    if (_attachments?.length) {
      await callApi('add_attachments', { entity_type: 'sc', entity_id: created.sc_id, file_paths: _attachments })
    }
    await searchScs()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}

async function handleSaveSubmit(data) {
  try {
    const { _attachments, ...formData } = data
    const created = await createDraft(formData)
    await submitSc(created.sc_id, formData)
    if (_attachments?.length) {
      await callApi('add_attachments', { entity_type: 'sc', entity_id: created.sc_id, file_paths: _attachments })
    }
    await searchScs()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}

async function handleExport() {
  exporting.value = true
  try {
    const columns = [
      { key: 'status', label: t('exportCol.status') },
      { key: 'sc_no', label: t('exportCol.scNo') },
      { key: 'requester_name', label: t('exportCol.requester') },
      { key: 'request_type', label: t('exportCol.type') },
      { key: 'cost_center', label: t('exportCol.costCenter') },
      { key: 'sc_amount', label: t('exportCol.scAmount') },
      { key: 'created_at', label: t('exportCol.created'), getValue: r => (r.created_at || '').slice(0, 19) },
      { key: 'description', label: t('exportCol.description') }
    ]
    await exportAll('search_scs', {
      filters: state.filters,
      sort: state.sort,
      direction: state.direction
    }, columns, `SC_List_${new Date().toISOString().slice(0, 10)}`)
    ElMessage.success(t('export.exported'))
  } catch (e) {
    ElMessage.error(e.message || t('export.failed'))
  } finally {
    exporting.value = false
  }
}

onMounted(async () => {
  try {
    activeUsers.value = await callApi('list_users')
  } catch { /* ignore */ }
  await searchScs()
})
</script>
