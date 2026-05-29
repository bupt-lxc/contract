<template>
  <div>
    <AdvancedFilterBar
      :filter-config="scFilterConfig"
      @filter="handleFilter"
      @reset="handleReset"
    >
      <template #actions>
        <el-button type="primary" @click="scDialogVisible = true; scDialogMode = 'create'">
          <el-icon><Plus /></el-icon> New SC
        </el-button>
      </template>
    </AdvancedFilterBar>

    <ScTable
      :rows="state.rows"
      :loading="state.loading"
      :empty-text="state.error || 'No SC records match the search and filters.'"
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
import { Plus } from '@element-plus/icons-vue'
import { useSc } from '@/composables/useSc.js'
import { callApi } from '@/api/bridge.js'
import AdvancedFilterBar from '@/components/common/AdvancedFilterBar.vue'
import ScTable from '@/components/sc/ScTable.vue'
import ScFormDialog from '@/components/sc/ScFormDialog.vue'
import { ElMessage } from 'element-plus'

const { state, searchScs, createDraft, submitSc, setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange } = useSc()

const scStatuses = [
  { label: 'Pending', value: 'pending' }, { label: 'Approved', value: 'approved' },
  { label: 'Denied', value: 'denied' }, { label: 'Closed', value: 'closed' }
]
const requestTypes = ['material', 'service', 'fixed_asset', 'FC']
const activeUsers = ref([])

const scFilterConfig = [
  { name: 'status', label: 'Status', type: 'select', options: scStatuses },
  { name: 'request_type', label: 'Request Type', type: 'select', options: requestTypes.map(t => ({ label: t, value: t })) },
  { name: 'cost_center', label: 'Cost Center', type: 'input' },
  { name: 'sc_id', label: 'SC ID', type: 'input' },
  { name: 'sc_no', label: 'SC No', type: 'input' },
  { name: 'requester_id', label: 'Requester', type: 'input' },
  { name: 'created_by', label: 'Created By', type: 'input' },
  { name: 'service_period_start', label: 'Service Start', type: 'date-range' },
  { name: 'sc_amount', label: 'SC Amount', type: 'amount-range' },
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
    await createDraft(data)
    await searchScs()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}

async function handleSaveSubmit(data) {
  try {
    const created = await createDraft(data)
    await submitSc(created.sc_id, data)
    await searchScs()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}

onMounted(async () => {
  try {
    activeUsers.value = await callApi('list_users')
  } catch { /* ignore */ }
  await searchScs()
})
</script>
