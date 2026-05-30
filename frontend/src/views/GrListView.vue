<template>
  <div>
    <AdvancedFilterBar
      :filter-config="grFilterConfig"
      @filter="handleFilter"
      @reset="handleReset"
    />

    <div style="margin-bottom:12px">
      <el-button @click="handleExport" :loading="exporting">
        <el-icon><Download /></el-icon> {{ $t('common.export') }}
      </el-button>
    </div>

    <el-table :data="state.rows" v-loading="state.loading" stripe border @row-click="handleRowClick">
      <el-table-column :label="$t('common.status')" width="100">
        <template #default="{ row }"><StatusBadge :status="row.status" /></template>
      </el-table-column>
      <el-table-column prop="gr_id" :label="$t('gr.grId')" width="120" />
      <el-table-column prop="po_no" :label="$t('gr.poNo')" width="130" />
      <el-table-column prop="sc_no" :label="$t('gr.scNo')" width="130" />
      <el-table-column prop="vendor_name" :label="$t('gr.vendor')" min-width="150" show-overflow-tooltip />
      <el-table-column prop="estimated_amount" :label="$t('gr.estimated')" width="120">
        <template #default="{ row }"><AmountDisplay :value="row.estimated_amount" /></template>
      </el-table-column>
      <el-table-column prop="con_value" :label="$t('gr.conValue')" width="120">
        <template #default="{ row }"><AmountDisplay :value="row.con_value" /></template>
      </el-table-column>
      <template #empty><el-empty :description="$t('gr.noRecords')" /></template>
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
import { useRouter } from 'vue-router'
import { Download } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import { useGr } from '@/composables/useGr.js'
import { useExport } from '@/composables/useExport.js'
import AdvancedFilterBar from '@/components/common/AdvancedFilterBar.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'
import { ElMessage } from 'element-plus'

const router = useRouter()
const { t } = useI18n()
const { state, searchGrs, setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange } = useGr()
const { exportAll } = useExport()
const exporting = ref(false)

const grStatuses = [
  { label: t('status.pending'), value: 'pending' }, { label: t('status.approved'), value: 'approved' }, { label: t('status.cancelled'), value: 'cancelled' }
]

const grFilterConfig = [
  { name: 'status', label: t('common.status'), type: 'select', options: grStatuses },
  { name: 'gr_id', label: t('gr.grId'), type: 'input' },
  { name: 'po_id', label: t('gr.poId'), type: 'input' },
  { name: 'sc_id', label: t('gr.scId'), type: 'input' },
  { name: 'requester_id', label: t('gr.requester'), type: 'input' },
  { name: 'vendor_id', label: t('gr.vendorId'), type: 'input' },
  { name: 'estimated_amount', label: t('gr.estAmount'), type: 'amount-range' },
  { name: 'con_value', label: t('gr.conValue'), type: 'amount-range' },
]

function handleFilter({ text, filters }) {
  searchGrs(text, filters)
}

function handleReset() {
  resetFilters()
  searchGrs()
}

function handleRowClick(row) {
  if (row.sc_id && row.po_id) {
    router.push(`/sc/${row.sc_id}/po/${row.po_id}/gr/${row.gr_id}`)
  }
}

function handlePageChange(page) { onPageChange(page); searchGrs() }
function handleSizeChange(size) { onPageSizeChange(size); searchGrs() }

async function handleExport() {
  exporting.value = true
  try {
    const columns = [
      { key: 'status', label: t('common.status') },
      { key: 'gr_id', label: t('gr.grId') },
      { key: 'po_no', label: t('gr.poNo') },
      { key: 'sc_no', label: t('gr.scNo') },
      { key: 'vendor_name', label: t('gr.vendor') },
      { key: 'estimated_amount', label: t('gr.estimated') },
      { key: 'con_value', label: t('gr.conValue') }
    ]
    await exportAll('search_grs', {
      filters: state.filters,
      sort: state.sort,
      direction: state.direction
    }, columns, `GR_List_${new Date().toISOString().slice(0, 10)}`)
    ElMessage.success(t('export.success'))
  } catch (e) {
    ElMessage.error(e.message || t('export.failed'))
  } finally {
    exporting.value = false
  }
}

onMounted(() => searchGrs())
</script>
