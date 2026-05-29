<template>
  <div>
    <FilterBar @reset="handleReset">
      <template #filters>
        <el-select v-model="filters.status" placeholder="Status" clearable @change="onFilterChange">
          <el-option v-for="s in scStatuses" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-select v-model="filters.request_type" placeholder="Request Type" clearable @change="onFilterChange">
          <el-option v-for="t in requestTypes" :key="t" :label="t" :value="t" />
        </el-select>
        <el-input v-model="filters.cost_center" placeholder="Cost Center" clearable @change="onFilterChange" style="width:150px" />
      </template>
      <template #actions>
        <el-button type="primary" @click="scDialogVisible = true; scDialogMode = 'create'">
          <el-icon><Plus /></el-icon> New SC
        </el-button>
      </template>
    </FilterBar>

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
import { ref, reactive, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { useSc } from '@/composables/useSc.js'
import { callApi } from '@/api/bridge.js'
import FilterBar from '@/components/common/FilterBar.vue'
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

const filters = reactive({ status: '', request_type: '', cost_center: '' })

const scDialogVisible = ref(false)
const scDialogMode = ref('create')
const scDialogRecord = ref(null)

function onFilterChange() {
  const f = {}
  if (filters.status) f.status = filters.status
  if (filters.request_type) f.request_type = filters.request_type
  if (filters.cost_center) f.cost_center = filters.cost_center
  setFilters(f)
  searchScs(null, f)
}

function handleReset() {
  Object.assign(filters, { status: '', request_type: '', cost_center: '' })
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
