<template>
  <div class="workbench">
    <h2 class="workbench-title">{{ $t('home.workbench') }}</h2>

    <div v-if="error" class="wb-error">
      {{ $t('home.loadError') }}: {{ error }}
    </div>

    <!-- Denied Section -->
    <div class="wb-row" v-if="deniedScCount > 0 || deniedGrCount > 0">
      <div class="wb-row__header">
        <span class="wb-row__label">{{ $t('home.denied') }}</span>
      </div>
      <div class="wb-grid wb-grid--2">
        <div
          v-if="deniedScCount > 0"
          class="wb-cell wb-cell--denied"
        >
          <div class="wb-cell__head wb-cell__head--denied">
            <span class="wb-cell__status">{{ $t('status.denied') }}</span>
            <span class="wb-cell__count">{{ deniedScCount }}</span>
          </div>
          <div class="wb-cell__table">
            <div class="wb-cell__th wb-cell__th--sc5">
              <span class="wb-cell__th-no">{{ $t('home.colScNo') }}</span>
              <span class="wb-cell__th-req">{{ $t('home.colRequester') }}</span>
              <span class="wb-cell__th-type">{{ $t('home.colRequestType') }}</span>
              <span class="wb-cell__th-amt">{{ $t('sc.scAmount') }}</span>
              <span class="wb-cell__th-date">{{ $t('home.colDeadline') }}</span>
            </div>
            <div
              v-for="row in (data.sc?.denied?.rows || [])"
              :key="row.sc_id"
              class="wb-cell__tr wb-cell__tr--sc5"
              @click="$router.push(`/sc/${row.sc_id}`)"
            >
              <span class="wb-cell__td-no" :title="row.sc_no">{{ row.sc_no || shortId(row.sc_id) }}</span>
              <span class="wb-cell__td-req">{{ row.requester_name }}</span>
              <span class="wb-cell__td-type">{{ row.request_type }}</span>
              <span class="wb-cell__td-amt">{{ formatCurrency(row.sc_amount) }}</span>
              <span class="wb-cell__td-date">{{ (row.deadline || '').slice(0, 10) || '-' }}</span>
            </div>
            <div v-if="!data.sc?.denied?.rows?.length" class="wb-cell__empty">—</div>
          </div>
          <div class="wb-cell__link" @click="$router.push('/sc?status=denied')">{{ $t('home.viewAllOfType') }}</div>
        </div>
        <div
          v-if="deniedGrCount > 0"
          class="wb-cell wb-cell--denied"
        >
          <div class="wb-cell__head wb-cell__head--denied">
            <span class="wb-cell__status">{{ $t('status.denied') }}</span>
            <span class="wb-cell__count">{{ deniedGrCount }}</span>
          </div>
          <div class="wb-cell__table">
            <div class="wb-cell__th">
              <span class="wb-cell__th-id">{{ $t('home.colGrId') }}</span>
              <span class="wb-cell__th-sub">{{ $t('home.colRequester') }}</span>
              <span class="wb-cell__th-date">{{ $t('home.colCreatedAt') }}</span>
            </div>
            <div
              v-for="row in (data.gr?.denied?.rows || [])"
              :key="row.gr_id"
              class="wb-cell__tr"
              @click="$router.push(`/sc/${row.sc_id}/po/${row.po_id}/gr/${row.gr_id}`)"
            >
              <span class="wb-cell__td-id" :title="row.gr_id">{{ shortId(row.gr_id) }}</span>
              <span class="wb-cell__td-sub">{{ row.requester_name }}</span>
              <span class="wb-cell__td-date">{{ (row.created_at || '').slice(0, 10) || '-' }}</span>
            </div>
            <div v-if="!data.gr?.denied?.rows?.length" class="wb-cell__empty">—</div>
          </div>
          <div class="wb-cell__link" @click="$router.push('/gr?status=denied')">{{ $t('home.viewAllOfType') }}</div>
        </div>
      </div>
    </div>

    <!-- SC Row -->
    <div class="wb-row">
      <div class="wb-row__header">
        <span class="wb-row__label">SC</span>
        <el-button type="primary" link size="small" @click="$router.push('/sc')">
          {{ $t('common.viewAll') }} <el-icon><ArrowRight /></el-icon>
        </el-button>
      </div>
      <div class="wb-grid wb-grid--2">
        <div v-for="cell in scRow1" :key="cell.status" :class="['wb-cell', `wb-cell--${headStatus(cell.status)}`]">
          <div :class="['wb-cell__head', `wb-cell__head--${headStatus(cell.status)}`]">
            <span class="wb-cell__status">{{ cell.label }}</span>
            <span class="wb-cell__count">{{ data.sc?.[cell.status]?.count ?? 0 }}</span>
          </div>
          <div class="wb-cell__table">
            <div class="wb-cell__th wb-cell__th--sc5">
              <span class="wb-cell__th-no">{{ $t('home.colScNo') }}</span>
              <span class="wb-cell__th-req">{{ $t('home.colRequester') }}</span>
              <span class="wb-cell__th-type">{{ $t('home.colType') }}</span>
              <span class="wb-cell__th-amt">{{ $t('home.colAmount') }}</span>
              <span class="wb-cell__th-date">{{ dateColLabel(cell.status) }}</span>
            </div>
            <div
              v-for="row in (data.sc?.[cell.status]?.rows || [])"
              :key="row.sc_id"
              class="wb-cell__tr wb-cell__tr--sc5"
              @click="$router.push(`/sc/${row.sc_id}`)"
            >
              <span class="wb-cell__td-no" :title="row.sc_no">{{ row.sc_no || shortId(row.sc_id) }}</span>
              <span class="wb-cell__td-req">{{ row.requester_name }}</span>
              <span class="wb-cell__td-type">{{ typeLabel(row.request_type) }}</span>
              <span class="wb-cell__td-amt">{{ formatCurrency(row.sc_amount, row.currency) }}</span>
              <span class="wb-cell__td-date">{{ cellDate(cell.status, row) }}</span>
            </div>
            <div v-if="!data.sc?.[cell.status]?.rows?.length" class="wb-cell__empty">—</div>
          </div>
          <div class="wb-cell__link" @click="$router.push(`/sc?status=${cell.status}`)">{{ $t('home.viewAllOfType') }}</div>
        </div>
      </div>
    </div>

    <!-- SC Row 2: pending + approved -->
    <div class="wb-row">
      <div class="wb-grid wb-grid--2">
        <div v-for="cell in scRow2" :key="cell.status" :class="['wb-cell', `wb-cell--${headStatus(cell.status)}`]">
          <div :class="['wb-cell__head', `wb-cell__head--${headStatus(cell.status)}`]">
            <span class="wb-cell__status">{{ cell.label }}</span>
            <span class="wb-cell__count">{{ data.sc?.[cell.status]?.count ?? 0 }}</span>
          </div>
          <div class="wb-cell__table">
            <div class="wb-cell__th wb-cell__th--sc5">
              <span class="wb-cell__th-no">{{ $t('home.colScNo') }}</span>
              <span class="wb-cell__th-req">{{ $t('home.colRequester') }}</span>
              <span class="wb-cell__th-type">{{ $t('home.colType') }}</span>
              <span class="wb-cell__th-amt">{{ $t('home.colAmount') }}</span>
              <span class="wb-cell__th-date">{{ dateColLabel(cell.status) }}</span>
            </div>
            <div
              v-for="row in (data.sc?.[cell.status]?.rows || [])"
              :key="row.sc_id"
              class="wb-cell__tr wb-cell__tr--sc5"
              @click="$router.push(`/sc/${row.sc_id}`)"
            >
              <span class="wb-cell__td-no" :title="row.sc_no">{{ row.sc_no || shortId(row.sc_id) }}</span>
              <span class="wb-cell__td-req">{{ row.requester_name }}</span>
              <span class="wb-cell__td-type">{{ typeLabel(row.request_type) }}</span>
              <span class="wb-cell__td-amt">{{ formatCurrency(row.sc_amount, row.currency) }}</span>
              <span class="wb-cell__td-date">{{ cellDate(cell.status, row) }}</span>
            </div>
            <div v-if="!data.sc?.[cell.status]?.rows?.length" class="wb-cell__empty">—</div>
          </div>
          <div class="wb-cell__link" @click="$router.push(`/sc?status=${cell.status}`)">{{ $t('home.viewAllOfType') }}</div>
        </div>
      </div>
    </div>

    <!-- PO Row -->
    <div class="wb-row">
      <div class="wb-row__header">
        <span class="wb-row__label">PO</span>
        <el-button type="primary" link size="small" @click="$router.push('/po')">
          {{ $t('common.viewAll') }} <el-icon><ArrowRight /></el-icon>
        </el-button>
      </div>
      <div class="wb-grid wb-grid--po">
        <div v-for="cell in poCells" :key="cell.status" :class="['wb-cell', `wb-cell--${headStatus(cell.status)}`, { 'wb-cell--span2': cell.status === 'active' }]">
          <div :class="['wb-cell__head', `wb-cell__head--${headStatus(cell.status)}`]">
            <span class="wb-cell__status">{{ cell.label }}</span>
            <span class="wb-cell__count">{{ data.po?.[cell.status]?.count ?? 0 }}</span>
          </div>
          <div class="wb-cell__table">
            <!-- Draft: PO No | SC NO | Requester | Created At -->
            <template v-if="cell.status === 'draft'">
              <div class="wb-cell__th">
                <span class="wb-cell__th-id">{{ $t('home.colPoNo') }}</span>
                <span class="wb-cell__th-sc">{{ $t('home.colScNo') }}</span>
                <span class="wb-cell__th-sub">{{ $t('home.colRequester') }}</span>
                <span class="wb-cell__th-date">{{ $t('home.colCreatedAt') }}</span>
              </div>
              <div
                v-for="row in (data.po?.[cell.status]?.rows || [])"
                :key="row.po_id"
                class="wb-cell__tr"
                @click="$router.push(`/sc/${row.sc_id}/po/${row.po_id}`)"
              >
                <span class="wb-cell__td-id" :title="row.po_id">{{ row.po_no || shortId(row.po_id) }}</span>
                <span class="wb-cell__td-sc">{{ row.sc_no }}</span>
                <span class="wb-cell__td-sub">{{ row.requester_name }}</span>
                <span class="wb-cell__td-date">{{ (row.created_at || '').slice(0, 10) || '-' }}</span>
              </div>
            </template>
            <!-- Activating: PO No | SC NO | Requester | Start Day | End Day | Open PO Amt -->
            <template v-else>
              <div class="wb-cell__th wb-cell__th--activating">
                <span class="wb-cell__th-id">{{ $t('home.colPoNo') }}</span>
                <span class="wb-cell__th-sc">{{ $t('home.colScNo') }}</span>
                <span class="wb-cell__th-sub">{{ $t('home.colRequester') }}</span>
                <span class="wb-cell__th-day">{{ $t('home.colStartDay') }}</span>
                <span class="wb-cell__th-day">{{ $t('home.colEndDay') }}</span>
                <span class="wb-cell__th-amt">{{ $t('home.colOpenPoAmount') }}</span>
              </div>
              <div
                v-for="row in (data.po?.[cell.status]?.rows || [])"
                :key="row.po_id"
                class="wb-cell__tr wb-cell__tr--activating"
                @click="$router.push(`/sc/${row.sc_id}/po/${row.po_id}`)"
              >
                <span class="wb-cell__td-id" :title="row.po_id">{{ row.po_no || shortId(row.po_id) }}</span>
                <span class="wb-cell__td-sc">{{ row.sc_no }}</span>
                <span class="wb-cell__td-sub">{{ row.requester_name }}</span>
                <span class="wb-cell__td-day">{{ (row.contract_from || '').slice(0, 10) || '-' }}</span>
                <span class="wb-cell__td-day">{{ (row.contract_to || '').slice(0, 10) || '-' }}</span>
                <span class="wb-cell__td-amt">{{ formatCurrency(row.open_po_amount, row.currency) }}</span>
              </div>
            </template>
            <div v-if="!data.po?.[cell.status]?.rows?.length" class="wb-cell__empty">—</div>
          </div>
          <div class="wb-cell__link" @click="$router.push(`/po?status=${cell.status}`)">{{ $t('home.viewAllOfType') }}</div>
        </div>
      </div>
    </div>

    <!-- GR Row -->
    <div class="wb-row">
      <div class="wb-row__header">
        <span class="wb-row__label">GR</span>
        <el-button type="primary" link size="small" @click="$router.push('/gr')">
          {{ $t('common.viewAll') }} <el-icon><ArrowRight /></el-icon>
        </el-button>
      </div>
      <div :class="['wb-grid', 'wb-grid--4']">
        <div v-for="cell in grCells" :key="cell.status" :class="['wb-cell', `wb-cell--${headStatus(cell.status)}`]">
          <div :class="['wb-cell__head', `wb-cell__head--${headStatus(cell.status)}`]">
            <span class="wb-cell__status">{{ cell.label }}</span>
            <span class="wb-cell__count">{{ data.gr?.[cell.status]?.count ?? 0 }}</span>
          </div>
          <div class="wb-cell__table">
            <div class="wb-cell__th">
              <span class="wb-cell__th-id">{{ $t('home.colGrId') }}</span>
              <span class="wb-cell__th-sub">{{ $t('home.colRequester') }}</span>
              <span class="wb-cell__th-date">{{ dateColLabel(cell.status) }}</span>
            </div>
            <div
              v-for="row in (data.gr?.[cell.status]?.rows || [])"
              :key="row.gr_id"
              class="wb-cell__tr"
              @click="$router.push(`/sc/${row.sc_id}/po/${row.po_id}/gr/${row.gr_id}`)"
            >
              <span class="wb-cell__td-id" :title="row.gr_id">{{ shortId(row.gr_id) }}</span>
              <span class="wb-cell__td-sub">{{ row.requester_name }}</span>
              <span class="wb-cell__td-date">{{ cellDate(cell.status, row) }}</span>
            </div>
            <div v-if="!data.gr?.[cell.status]?.rows?.length" class="wb-cell__empty">—</div>
          </div>
          <div class="wb-cell__link" @click="$router.push(`/gr?status=${cell.status}`)">{{ $t('home.viewAllOfType') }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowRight } from '@element-plus/icons-vue'
import { callApi } from '@/api/bridge.js'

const { t } = useI18n()

const data = ref({ sc: {}, po: {}, gr: {} })
const error = ref(null)

const scRow1 = computed(() => [
  { status: 'draft',            label: t('status.draft') },
  { status: 'manager_confirm',  label: t('status.manager_confirm') },
])

const scRow2 = computed(() => [
  { status: 'pending',          label: t('status.pending') },
  { status: 'approved',         label: t('status.approved') },
])

const poCells = computed(() => [
  { status: 'draft',    label: t('status.draft') },
  { status: 'active', label: t('status.active') },
])

const grCells = computed(() => [
  { status: 'draft',            label: t('status.draft') },
  { status: 'manager_confirm',  label: t('status.manager_confirm') },
  { status: 'pending',          label: t('status.pending') },
  { status: 'approved',         label: t('status.approved') },
])

const deniedScCount = computed(() => data.value.sc?.denied?.count ?? 0)
const deniedGrCount = computed(() => data.value.gr?.denied?.count ?? 0)

function headStatus(status) {
  if (status.includes('draft')) return 'draft'
  if (status.includes('manager')) return 'manager'
  if (status.includes('active')) return 'pending'
  if (status.includes('pending')) return 'pending'
  if (status.includes('approved')) return 'approved'
  if (status.includes('finished')) return 'approved'
  if (status.includes('denied')) return 'denied'
  return 'draft'
}

function shortId(id) {
  if (!id) return '-'
  const parts = id.split('-')
  return parts.slice(2).join('-')
}

function typeLabel(requestType) {
  if (!requestType) return '-'
  const map = { material: 'M', service: 'S', fixed_asset: 'FA', FC: 'FC' }
  return map[requestType] || requestType
}

function formatCurrency(val, currency) {
  if (val == null || isNaN(val)) return '-'
  const symbols = { CNY: '¥', EUR: '€', USD: '$' }
  const prefix = symbols[currency] || ''
  return prefix + Number(val).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function dateColLabel(status) {
  if (status === 'draft') return t('home.colCreatedAt')
  if (status === 'manager_confirm') return t('home.colSubmitted')
  if (status === 'approved' || status === 'finished') return t('home.colDeadline')
  return t('home.colPendingDate')
}

function cellDate(status, row) {
  let val
  if (status === 'draft') val = row.created_at
  else if (status === 'manager_confirm') val = row.submitted_date
  else if (status === 'approved' || status === 'finished') val = row.deadline
  else val = row.pending_date
  return (val || '').slice(0, 10) || '-'
}

onMounted(async () => {
  try {
    data.value = await callApi('workbench_data')
  } catch (e) {
    error.value = e.message || String(e)
    console.error('[Workbench] load failed:', e)
  }
})
</script>

<style scoped>
.workbench {
  width: 100%;
  container-type: inline-size;
}

.workbench-title {
  margin-bottom: 0.8em;
  font-size: 1.25rem;
  font-weight: 700;
  color: #1e293b;
}

.wb-error {
  padding: 0.6em 0.8em;
  margin-bottom: 0.8em;
  border-radius: 6px;
  background: #fef2f2;
  color: #991b1b;
  font-size: 0.8rem;
}

/* Row */
.wb-row {
  margin-bottom: 1em;
}

.wb-row__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.35em;
  padding: 0 2px;
}

.wb-row__label {
  font-size: 0.95rem;
  font-weight: 700;
  color: #334155;
  letter-spacing: 0.05em;
}

/* Grid */
.wb-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: clamp(6px, 1%, 12px);
}

.wb-grid--2 {
  grid-template-columns: repeat(2, 1fr);
}

.wb-grid--4 {
  grid-template-columns: repeat(4, 1fr);
}

.wb-grid--2 {
  grid-template-columns: repeat(2, 1fr);
}

.wb-grid--po {
  grid-template-columns: repeat(3, 1fr);
}

.wb-cell--span2 {
  grid-column: span 2;
}

/* Cell */
.wb-cell {
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  overflow: hidden;
  min-width: 0;
  background: #fff;
  color: #1e293b;
}

.wb-cell__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5em 0.7em;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
}

.wb-cell__status {
  font-size: 0.8rem;
  font-weight: 600;
  color: #475569;
}

.wb-cell__count {
  font-size: 1.2rem;
  font-weight: 700;
  color: #1e293b;
}

/* Status colors — head */
.wb-cell__head--draft    { background: #f8fafc; }
.wb-cell__head--manager  { background: #eff6ff; }
.wb-cell__head--pending  { background: #fff7ed; }
.wb-cell__head--approved { background: #f0fdf4; }

/* Table area — single background, children transparent */
.wb-cell--draft .wb-cell__table    { background: #fafbfc; }
.wb-cell--manager .wb-cell__table  { background: #f8fafd; }
.wb-cell--pending .wb-cell__table  { background: #fefaf5; }
.wb-cell--approved .wb-cell__table { background: #f6fcf7; }

.wb-cell__head--denied    { background: #fef2f2; }
.wb-cell--denied .wb-cell__table { background: #fefaf9; }

.wb-cell__th,
.wb-cell__tr,
.wb-cell__empty {
  background: transparent;
}

/* Table */
.wb-cell__table {
  padding: 0;
}

.wb-cell__th {
  display: flex;
  align-items: center;
  padding: 0.35em 0.7em;
  gap: 0.4em;
  border-bottom: 1px solid #e8ecf0;
  font-size: 0.68rem;
  font-weight: 600;
  color: #94a3b8;
  letter-spacing: 0.03em;
  line-height: 1.3;
}

.wb-cell__th-id,
.wb-cell__td-id {
  flex: 1 1 32%;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wb-cell__th-sub,
.wb-cell__td-sub {
  flex: 0 0 30%;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wb-cell__th-date,
.wb-cell__td-date {
  flex: 0 0 22%;
  min-width: 0;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* SC 5-column layout */
.wb-cell__th--sc5 .wb-cell__th-no,
.wb-cell__tr--sc5 .wb-cell__td-no {
  flex: 1 1 24%;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wb-cell__th--sc5 .wb-cell__th-req,
.wb-cell__tr--sc5 .wb-cell__td-req {
  flex: 0 0 19%;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wb-cell__th--sc5 .wb-cell__th-type,
.wb-cell__tr--sc5 .wb-cell__td-type {
  flex: 0 0 10%;
  min-width: 0;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wb-cell__th--sc5 .wb-cell__th-amt,
.wb-cell__tr--sc5 .wb-cell__td-amt {
  flex: 0 0 20%;
  min-width: 0;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wb-cell__th--sc5 .wb-cell__th-date,
.wb-cell__tr--sc5 .wb-cell__td-date {
  flex: 0 0 18%;
  min-width: 0;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* SC NO column (PO) */
.wb-cell__th-sc,
.wb-cell__td-sc {
  flex: 0 0 18%;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Activating: 6-column layout */
.wb-cell__th--activating .wb-cell__th-id,
.wb-cell__tr--activating .wb-cell__td-id {
  flex: 1 1 20%;
}

.wb-cell__th--activating .wb-cell__th-sc,
.wb-cell__tr--activating .wb-cell__td-sc {
  flex: 0 0 14%;
}

.wb-cell__th--activating .wb-cell__th-sub,
.wb-cell__tr--activating .wb-cell__td-sub {
  flex: 0 0 14%;
}

.wb-cell__th-day,
.wb-cell__td-day {
  flex: 0 0 16%;
  min-width: 0;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wb-cell__th-amt,
.wb-cell__td-amt {
  flex: 0 0 18%;
  min-width: 0;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* SC 5-column layout for denied section */
.wb-cell__th--sc5 .wb-cell__th-no,
.wb-cell__tr--sc5 .wb-cell__td-no {
  flex: 1 1 22%;
}

.wb-cell__th--sc5 .wb-cell__th-req,
.wb-cell__tr--sc5 .wb-cell__td-req {
  flex: 0 0 18%;
}

.wb-cell__th--sc5 .wb-cell__th-type,
.wb-cell__tr--sc5 .wb-cell__td-type {
  flex: 0 0 14%;
}

.wb-cell__th--sc5 .wb-cell__th-amt,
.wb-cell__tr--sc5 .wb-cell__td-amt {
  flex: 0 0 20%;
}

.wb-cell__th--sc5 .wb-cell__th-date,
.wb-cell__tr--sc5 .wb-cell__td-date {
  flex: 0 0 22%;
}

.wb-cell__th-no,
.wb-cell__td-no {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wb-cell__th-req,
.wb-cell__td-req {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wb-cell__th-type,
.wb-cell__td-type {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wb-cell__tr {
  display: flex;
  align-items: center;
  padding: 0.45em 0.7em;
  gap: 0.4em;
  cursor: pointer;
  transition: background 0.12s, filter 0.12s;
  border-bottom: 1px solid rgba(0,0,0,0.04);
  line-height: 1.3;
}

.wb-cell__tr:last-child {
  border-bottom: none;
}

.wb-cell__tr:hover {
  filter: brightness(0.97);
}

.wb-cell__td-id {
  font-size: 0.78rem;
  font-weight: 600;
  color: #1e293b;
}

.wb-cell__td-sub {
  font-size: 0.72rem;
  color: #94a3b8;
}

.wb-cell__td-date {
  font-size: 0.68rem;
  color: #94a3b8;
}

.wb-cell__td-no {
  font-size: 0.78rem;
  font-weight: 600;
  color: #1e293b;
}

.wb-cell__td-type {
  font-size: 0.68rem;
  font-weight: 600;
  color: #64748b;
}

.wb-cell__td-amt {
  font-size: 0.72rem;
  color: #475569;
}

.wb-cell__empty {
  padding: 1em 0.7em;
  text-align: center;
  font-size: 0.75rem;
  color: #cbd5e1;
}

.wb-cell__link {
  padding: 0.35em 0.7em;
  text-align: center;
  font-size: 0.7rem;
  color: #3b82f6;
  cursor: pointer;
  border-top: 1px solid #e8ecf0;
  transition: background 0.12s;
}

.wb-cell__link:hover {
  background: rgba(59, 130, 246, 0.06);
}
</style>
