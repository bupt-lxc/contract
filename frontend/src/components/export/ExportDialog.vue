<template>
  <el-dialog
    :model-value="visible"
    :title="dialogTitle"
    width="520px"
    @update:model-value="$emit('update:visible', $event)"
    @close="handleClose"
  >
    <el-form label-position="top">
      <!-- Format selector -->
      <el-form-item :label="$t('export.format')">
        <el-radio-group v-model="exportFormat">
          <el-radio value="xlsx">{{ $t('export.xlsx') }}</el-radio>
          <el-radio value="csv">{{ $t('export.csv') }}</el-radio>
        </el-radio-group>
        <div v-if="exportFormat === 'csv'" style="color:#909399;font-size:12px;margin-top:4px">
          {{ $t('export.formatCSVHint') }}
        </div>
      </el-form-item>

      <!-- Cascade options -->
      <template v-if="entityType === 'sc'">
        <el-form-item :label="$t('export.cascadeOptions')">
          <el-checkbox v-model="cascadePo" @change="onCascadePoChange">
            {{ $t('export.includeRelatedPos') }}
          </el-checkbox>
          <el-checkbox v-model="cascadeGr" :disabled="!cascadePo" style="margin-left:24px">
            {{ $t('export.includeRelatedGrs') }}
          </el-checkbox>
        </el-form-item>
      </template>
      <template v-if="entityType === 'po'">
        <el-form-item :label="$t('export.cascadeOptions')">
          <el-checkbox v-model="cascadeGr">
            {{ $t('export.includeRelatedGrs') }}
          </el-checkbox>
        </el-form-item>
      </template>

      <!-- Data scope -->
      <el-form-item :label="$t('export.dataScope')">
        <el-radio-group v-model="dataScope">
          <el-radio v-if="selectedCount > 0" value="selected">
            {{ $t('export.selectedRows', { count: selectedCount }) }}
          </el-radio>
          <el-radio v-if="hasFilters" value="filtered">
            {{ $t('export.filteredRows', { count: filteredCount }) }}
          </el-radio>
          <el-radio value="all">
            {{ $t('export.allRows', { count: totalCount }) }}
          </el-radio>
        </el-radio-group>
      </el-form-item>

      <!-- Filename -->
      <el-form-item :label="$t('export.filename')">
        <el-input v-model="filename" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">{{ $t('common.cancel') }}</el-button>
      <el-button type="primary" :loading="exporting" @click="doExport">
        {{ $t('common.export') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { callApi } from '@/api/bridge.js'
import { useExport } from '@/composables/useExport.js'
import { ElMessage } from 'element-plus'

const { t } = useI18n()
const { exportMultiSheet, exportCSV } = useExport()

const props = defineProps({
  visible: { type: Boolean, default: false },
  entityType: { type: String, required: true },
  filters: { type: Object, default: () => ({}) },
  sort: { type: String, default: 'created_at' },
  direction: { type: String, default: 'desc' },
  selectedIds: { type: Array, default: () => [] },
  filteredCount: { type: Number, default: 0 },
  totalCount: { type: Number, default: 0 },
})

const emit = defineEmits(['update:visible', 'exported'])

const cascadePo = ref(false)
const cascadeGr = ref(false)
const dataScope = ref(initScope())
const exportFormat = ref('xlsx')
const filename = ref(defaultFilename())
const exporting = ref(false)

function initScope() {
  if (props.selectedIds.length) return 'selected'
  if (Object.keys(props.filters).some(k => props.filters[k] !== '' && props.filters[k] != null)) return 'filtered'
  return 'all'
}

function defaultFilename() {
  const date = new Date().toISOString().slice(0, 10)
  const label = { sc: 'SC', po: 'PO', gr: 'GR' }[props.entityType]
  return `${label}_Export_${date}`
}

const dialogTitle = computed(() => t('export.dialogTitle', { type: { sc: 'SC', po: 'PO', gr: 'GR' }[props.entityType] }))
const selectedCount = computed(() => props.selectedIds.length)
const hasFilters = computed(() => Object.keys(props.filters).some(k => props.filters[k] !== '' && props.filters[k] != null))

function onCascadePoChange(val) {
  if (!val) cascadeGr.value = false
}

function handleClose() {
  cascadePo.value = false
  cascadeGr.value = false
  dataScope.value = initScope()
}

const CASCADE_COLUMNS = [
  // Shared columns
  { key: '_type', label: t('export.entryType') },
  { key: 'sc_id', label: 'SC ID' },
  { key: 'sc_no', label: t('export.scNo') },
  { key: 'po_id', label: 'PO ID' },
  { key: 'po_no', label: t('export.poNo') },
  { key: 'gr_id', label: 'GR ID' },
  { key: 'gr_no', label: t('export.grNo') },
  { key: 'status', label: t('export.status') },
  { key: 'requester_name', label: t('export.requester') },
  { key: 'cost_center', label: t('export.costCenter') },
  // SC-specific
  { key: 'request_type', label: t('export.type') },
  { key: 'sc_amount', label: t('export.scAmount') },
  { key: 'currency', label: t('sc.currency') },
  { key: 'calloff_po_id', label: t('exportCol.calloffPoId') },
  { key: 'service_period_start', label: t('sc.startDate'), getValue: r => (r.service_period_start || '').slice(0, 10) },
  { key: 'service_period_end', label: t('sc.endDate'), getValue: r => (r.service_period_end || '').slice(0, 10) },
  { key: 'asset_nums', label: t('exportCol.assetNums') },
  { key: 'internal_system_number', label: t('exportCol.internalSystemNumber') },
  { key: 'service_scope', label: t('vendor.serviceScope') },
  // PO-specific
  { key: 'vendor_name', label: t('export.vendorName') },
  { key: 'ksrm_vendor_code', label: t('export.ksrmCode') },
  { key: 'po_amount', label: t('export.poAmount') },
  { key: 'open_po_amount', label: t('export.openPoAmount') },
  { key: 'po_pending_total_incl_tax', label: t('po.pendingInclTax') },
  { key: 'consumed_amount', label: t('po.consumedAmount') },
  { key: 'contract_from', label: t('export.contractFrom'), getValue: r => (r.contract_from || '').slice(0, 10) },
  { key: 'contract_to', label: t('export.contractTo'), getValue: r => (r.contract_to || '').slice(0, 10) },
  { key: 'contract_no', label: t('po.contractNo') },
  { key: 'payment_frequency', label: t('po.paymentFrequency') },
  { key: 'contract_pos', label: t('exportCol.contractPos') },
  { key: 'contract_type', label: t('exportCol.contractType') },
  { key: 'purchaser', label: t('exportCol.purchaser') },
  { key: 'active_date', label: t('exportCol.activeDate'), getValue: r => (r.active_date || '').slice(0, 10) },
  // GR-specific
  { key: 'estimated_amount', label: t('export.estimated') },
  { key: 'con_value', label: t('export.conValue') },
  { key: 'gross_cost', label: t('export.grossCost') },
  { key: 'tax_rate', label: t('gr.taxRate') },
  { key: 'goods_service_description', label: t('gr.goodsServiceDescription') },
  { key: 'confirmation_name', label: t('gr.confirmationName') },
  { key: 'delivery_from', label: t('gr.deliveryFrom'), getValue: r => (r.delivery_from || '').slice(0, 10) },
  { key: 'delivery_to', label: t('gr.deliveryTo'), getValue: r => (r.delivery_to || '').slice(0, 10) },
  { key: 'last_delivery', label: t('gr.lastDelivery') },
  { key: 'is_cancellation', label: t('gr.isCancellation') },
  // Common timestamps
  { key: 'created_at', label: t('export.created'), getValue: r => {
    if (r.created_at && r.created_at.includes('T')) {
      return r.created_at.replace('T', ' ').slice(0, 19)
    }
    return (r.created_at || '').slice(0, 10)
  }},
  { key: 'submitted_date', label: t('sc.submittedDate'), getValue: r => (r.submitted_date || '').slice(0, 10) },
]

function buildSheets(cascadeRows, statistics) {
  const sheets = []

  // Sheet 1: Cascade data
  sheets.push({
    name: t('export.sheetData'),
    rows: cascadeRows,
    columns: CASCADE_COLUMNS,
  })

  // Sheet 2: Overview
  const overviewCols = buildOverviewColumns(statistics.overview)
  if (overviewCols.length) {
    const overviewRows = buildOverviewRows(statistics.overview, overviewCols)
    sheets.push({ name: t('export.sheetOverview'), rows: overviewRows, columns: overviewCols })
  }

  // Sheet 3: Financial
  sheets.push({
    name: t('export.sheetFinancial'),
    rows: statistics.financial || [],
    columns: [
      { key: 'year', label: t('export.year') },
      { key: 'month', label: t('export.month') },
      { key: 'sc_amount', label: t('export.scAmount') },
      { key: 'po_amount', label: t('export.poAmount') },
      { key: 'gr_est_amount', label: t('export.grEstAmount') },
      { key: 'gr_con_amount', label: t('export.grConAmount') },
      { key: 'gr_gross_amount', label: t('export.grGrossAmount') },
    ],
  })

  // Sheet 4: Budget Health (only if present)
  if (statistics.budget_health) {
    sheets.push({
      name: t('export.sheetBudgetHealth'),
      rows: statistics.budget_health,
      columns: [
        { key: 'sc_no', label: t('export.scNo') },
        { key: 'sc_amount', label: t('export.scAmount') },
        { key: 'allocated_po', label: t('export.allocatedPo') },
        { key: 'po_balance', label: t('export.poBalance') },
        { key: 'gr_pending_tax', label: t('export.grPendingTax') },
        { key: 'gr_consumed', label: t('export.grConsumed') },
        { key: 'health', label: t('export.healthStatus') },
      ],
    })
  }

  // Sheet 5: Processing Time
  sheets.push({
    name: t('export.sheetProcessing'),
    rows: statistics.processing || [],
    columns: [
      { key: 'entity', label: t('export.entityType') },
      { key: 'stage', label: t('export.stage') },
      { key: 'avg_days', label: t('export.avgDays') },
      { key: 'min_days', label: t('export.minDays') },
      { key: 'max_days', label: t('export.maxDays') },
    ],
  })

  // Sheet 6: By Requester
  sheets.push({
    name: t('export.sheetByRequester'),
    rows: statistics.by_requester || [],
    columns: [
      { key: 'requester_name', label: t('export.requester') },
      { key: 'sc_count', label: t('export.scCount') },
      { key: 'sc_amount', label: t('export.scAmount') },
      { key: 'po_count', label: t('export.poCount') },
      { key: 'po_amount', label: t('export.poAmount') },
      { key: 'gr_count', label: t('export.grCount') },
      { key: 'gr_est', label: t('export.grEstAmount') },
      { key: 'gr_con', label: t('export.grConAmount') },
    ],
  })

  return sheets
}

function buildOverviewColumns(overview) {
  const cols = [{ key: 'stat', label: t('export.statItem') }]
  if (overview.sc) {
    cols.push({ key: 'sc_count', label: 'SC' })
    cols.push({ key: 'sc_amount', label: t('export.scAmount') })
  }
  if (overview.po) {
    cols.push({ key: 'po_count', label: 'PO' })
    cols.push({ key: 'po_amount', label: t('export.poAmount') })
  }
  if (overview.gr) {
    cols.push({ key: 'gr_count', label: 'GR' })
    cols.push({ key: 'gr_est', label: t('export.grEstAmount') })
    cols.push({ key: 'gr_con', label: t('export.grConAmount') })
  }
  return cols
}

function buildOverviewRows(overview, cols) {
  const rows = []

  const addRow = (stat, data) => {
    const row = { stat }
    if (data.sc) { row.sc_count = data.sc.count; row.sc_amount = data.sc.amount }
    if (data.po) { row.po_count = data.po.count; row.po_amount = data.po.amount }
    if (data.gr) { row.gr_count = data.gr.count; row.gr_est = data.gr.est; row.gr_con = data.gr.con }
    rows.push(row)
  }

  if (overview.sc || overview.po || overview.gr) {
    addRow(t('export.totalCount'), {
      sc: overview.sc ? { count: overview.sc.total_count } : null,
      po: overview.po ? { count: overview.po.total_count } : null,
      gr: overview.gr ? { count: overview.gr.total_count } : null,
    })
    addRow(t('export.totalAmount'), {
      sc: overview.sc ? { amount: overview.sc.total_amount } : null,
      po: overview.po ? { amount: overview.po.total_amount } : null,
      gr: overview.gr ? { est: overview.gr.total_estimated_amount, con: overview.gr.total_con_value } : null,
    })
    const statuses = ['draft', 'manager_confirm', 'pending', 'approved', 'denied', 'finished']
    for (const status of statuses) {
      const scCount = overview.sc ? overview.sc[`${status}_count`] : null
      const poCount = overview.po ? overview.po[`${status}_count`] : null
      const grCount = overview.gr ? overview.gr[`${status}_count`] : null
      if (scCount || poCount || grCount) {
        addRow(`  ${status}`, {
          sc: scCount != null ? { count: scCount } : null,
          po: poCount != null ? { count: poCount } : null,
          gr: grCount != null ? { count: grCount } : null,
        })
      }
    }
  }
  return rows
}

async function doExport() {
  exporting.value = true
  try {
    let apiMethod

    if (props.entityType === 'sc') {
      apiMethod = 'export_scs_cascade'
    } else if (props.entityType === 'po') {
      apiMethod = 'export_pos_cascade'
    } else {
      apiMethod = 'export_grs_with_stats'
    }

    const payload = {
      filters: dataScope.value === 'all' ? {} : props.filters,
      sort: props.sort,
      direction: props.direction,
      cascade: { po: cascadePo.value, gr: cascadeGr.value },
      selected_ids: dataScope.value === 'selected' ? props.selectedIds : undefined,
    }

    const result = await callApi(apiMethod, payload)
    const { cascade_rows, statistics } = result

    if (exportFormat.value === 'csv') {
      await exportCSV(cascade_rows, CASCADE_COLUMNS, filename.value)
    } else {
      const sheets = buildSheets(cascade_rows, statistics)
      await exportMultiSheet(sheets, filename.value)
    }

    ElMessage.success(t('export.exported'))
    emit('update:visible', false)
    emit('exported')
  } catch (e) {
    ElMessage.error(e.message || t('export.failed'))
  } finally {
    exporting.value = false
  }
}
</script>
