<template>
  <div class="workbench">
    <h2 class="workbench-title">{{ $t('home.workbench') }}</h2>

    <div v-if="error" class="wb-error">
      {{ $t('home.loadError') }}: {{ error }}
    </div>

    <!-- SC Row -->
    <div class="wb-row">
      <div class="wb-row__header">
        <span class="wb-row__label">SC</span>
        <el-button type="primary" link size="small" @click="$router.push('/sc')">
          {{ $t('common.viewAll') }} <el-icon><ArrowRight /></el-icon>
        </el-button>
      </div>
      <div class="wb-grid">
        <div v-for="cell in scCells" :key="cell.status" :class="['wb-cell', `wb-cell--${headStatus(cell.status)}`]">
          <div :class="['wb-cell__head', `wb-cell__head--${headStatus(cell.status)}`]">
            <span class="wb-cell__status">{{ cell.label }}</span>
            <span class="wb-cell__count">{{ data.sc?.[cell.status]?.count ?? 0 }}</span>
          </div>
          <div class="wb-cell__table">
            <div class="wb-cell__th">
              <span class="wb-cell__th-id">{{ $t('home.colScNo') }}</span>
              <span class="wb-cell__th-sub">{{ $t('home.colRequester') }}</span>
              <span class="wb-cell__th-amt">{{ $t('home.colAmount') }}</span>
            </div>
            <div
              v-for="row in (data.sc?.[cell.status]?.rows || [])"
              :key="row.sc_id"
              class="wb-cell__tr"
              @click="$router.push(`/sc/${row.sc_id}`)"
            >
              <span class="wb-cell__td-id">{{ row.sc_no || row.sc_id }}</span>
              <span class="wb-cell__td-sub">{{ row.requester_name }}</span>
              <span class="wb-cell__td-amt"><AmountDisplay :value="row.sc_amount" /></span>
            </div>
            <div v-if="!data.sc?.[cell.status]?.rows?.length" class="wb-cell__empty">—</div>
          </div>
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
      <div class="wb-grid">
        <div v-for="cell in poCells" :key="cell.status" :class="['wb-cell', `wb-cell--${headStatus(cell.status)}`]">
          <div :class="['wb-cell__head', `wb-cell__head--${headStatus(cell.status)}`]">
            <span class="wb-cell__status">{{ cell.label }}</span>
            <span class="wb-cell__count">{{ data.po?.[cell.status]?.count ?? 0 }}</span>
          </div>
          <div class="wb-cell__table">
            <div class="wb-cell__th">
              <span class="wb-cell__th-id">{{ $t('home.colPoNo') }}</span>
              <span class="wb-cell__th-sub">{{ $t('home.colVendor') }}</span>
              <span class="wb-cell__th-amt">{{ $t('home.colAmount') }}</span>
            </div>
            <div
              v-for="row in (data.po?.[cell.status]?.rows || [])"
              :key="row.po_id"
              class="wb-cell__tr"
              @click="$router.push(`/sc/${row.sc_id}/po/${row.po_id}`)"
            >
              <span class="wb-cell__td-id">{{ row.po_no || row.po_id }}</span>
              <span class="wb-cell__td-sub">{{ row.vendor_name }}</span>
              <span class="wb-cell__td-amt"><AmountDisplay :value="row.po_amount" /></span>
            </div>
            <div v-if="!data.po?.[cell.status]?.rows?.length" class="wb-cell__empty">—</div>
          </div>
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
      <div class="wb-grid">
        <div v-for="cell in grCells" :key="cell.status" :class="['wb-cell', `wb-cell--${headStatus(cell.status)}`]">
          <div :class="['wb-cell__head', `wb-cell__head--${headStatus(cell.status)}`]">
            <span class="wb-cell__status">{{ cell.label }}</span>
            <span class="wb-cell__count">{{ data.gr?.[cell.status]?.count ?? 0 }}</span>
          </div>
          <div class="wb-cell__table">
            <div class="wb-cell__th">
              <span class="wb-cell__th-id">{{ $t('home.colGrId') }}</span>
              <span class="wb-cell__th-sub">{{ $t('home.colPoNo') }}</span>
              <span class="wb-cell__th-amt">{{ $t('home.colEstAmount') }}</span>
            </div>
            <div
              v-for="row in (data.gr?.[cell.status]?.rows || [])"
              :key="row.gr_id"
              class="wb-cell__tr"
              @click="$router.push(`/sc/${row.sc_id}/po/${row.po_id}`)"
            >
              <span class="wb-cell__td-id">{{ row.gr_id }}</span>
              <span class="wb-cell__td-sub">{{ row.po_no }}</span>
              <span class="wb-cell__td-amt"><AmountDisplay :value="row.estimated_amount" /></span>
            </div>
            <div v-if="!data.gr?.[cell.status]?.rows?.length" class="wb-cell__empty">—</div>
          </div>
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
import AmountDisplay from '@/components/common/AmountDisplay.vue'

const { t } = useI18n()

const data = ref({ sc: {}, po: {}, gr: {} })
const error = ref(null)

const scCells = computed(() => [
  { status: 'draft',     label: t('status.draft') },
  { status: 'pending',   label: t('status.pending') },
  { status: 'approved',  label: t('status.approved') },
])

const poCells = computed(() => [
  { status: 'draft',        label: t('status.draft') },
  { status: 'po_pending',   label: t('status.pending') },
  { status: 'po_approved',  label: t('status.approved') },
])

const grCells = computed(() => [
  { status: 'draft',      label: t('status.draft') },
  { status: 'pending',    label: t('status.pending') },
  { status: 'approved',   label: t('status.approved') },
])

function headStatus(status) {
  if (status.includes('draft')) return 'draft'
  if (status.includes('pending')) return 'pending'
  if (status.includes('approved')) return 'approved'
  return 'draft'
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

.wb-grid--4 {
  grid-template-columns: repeat(4, 1fr);
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

/* Status colors */
.wb-cell__head--draft {
  background: #f8fafc;
}
.wb-cell__head--pending {
  background: #fff7ed;
}
.wb-cell__head--approved {
  background: #f0fdf4;
}

.wb-cell--draft .wb-cell__tr {
  background: #fafbfc;
}
.wb-cell--pending .wb-cell__tr {
  background: #fffaf5;
}
.wb-cell--approved .wb-cell__tr {
  background: #f7fdf8;
}

.wb-cell--draft .wb-cell__empty {
  background: #fafbfc;
}
.wb-cell--pending .wb-cell__empty {
  background: #fffaf5;
}
.wb-cell--approved .wb-cell__empty {
  background: #f7fdf8;
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
  background: #fafbfc;
  border-bottom: 1px solid #f1f5f9;
  font-size: 0.68rem;
  font-weight: 600;
  color: #94a3b8;
  letter-spacing: 0.03em;
  line-height: 1.3;
}

.wb-cell__th-id,
.wb-cell__td-id {
  flex: 1 1 35%;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wb-cell__th-sub,
.wb-cell__td-sub {
  flex: 0 0 28%;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wb-cell__th-amt,
.wb-cell__td-amt {
  flex: 0 0 28%;
  min-width: 0;
  text-align: right;
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
  border-bottom: 1px solid #f8fafc;
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

.wb-cell__td-amt {
  font-size: 0.78rem;
  font-weight: 500;
  color: #334155;
}

.wb-cell__empty {
  padding: 1em 0.7em;
  text-align: center;
  font-size: 0.75rem;
  color: #cbd5e1;
}
</style>
