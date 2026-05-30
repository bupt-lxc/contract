<template>
  <div>
    <h2 style="margin-bottom:16px;font-size:20px;font-weight:700">{{ $t('home.workbench') }}</h2>
    <el-row :gutter="16">
      <el-col :span="12" v-for="card in cards" :key="card.title" style="margin-bottom:16px">
        <el-card shadow="hover" class="workbench-card">
          <template #header>
            <div class="card-header">
              <span>{{ card.title }}</span>
              <el-button type="primary" link size="small" @click="card.link">
                {{ $t('common.viewAll') }} <el-icon><ArrowRight /></el-icon>
              </el-button>
            </div>
          </template>
          <el-table :data="card.rows" size="small" @row-click="card.onRowClick" style="cursor:pointer">
            <el-table-column prop="status" :label="$t('export.status')" width="100">
              <template #default="{ row }"><StatusBadge :status="row.status" /></template>
            </el-table-column>
            <el-table-column :prop="card.idKey" :label="card.idLabel" min-width="120" />
            <el-table-column :prop="card.amountKey" :label="card.amountLabel" width="110">
              <template #default="{ row }"><AmountDisplay :value="row[card.amountKey]" /></template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!card.rows.length" :description="$t('home.noCards', { title: card.title })" :image-size="40" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ArrowRight } from '@element-plus/icons-vue'
import { callApi } from '@/api/bridge.js'
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'

const router = useRouter()
const { t } = useI18n()
const user = computed(() => window.__currentUser || {})
const isAdmin = computed(() => user.value?.role === 'admin')

const pendingScs = ref([])
const pendingPos = ref([])
const pendingGrs = ref([])
const drafts = ref([])
const deniedScs = ref([])

const cards = computed(() => {
  if (isAdmin.value) {
    return [
      { title: t('home.pendingScs'), rows: pendingScs.value.slice(0, 5), idKey: 'sc_no', idLabel: t('home.scNo'), amountKey: 'sc_amount', amountLabel: t('home.amount'), link: () => router.push('/sc'), onRowClick: row => router.push(`/sc/${row.sc_id}`) },
      { title: t('home.pendingPos'), rows: pendingPos.value.slice(0, 5), idKey: 'po_no', idLabel: t('home.poNo'), amountKey: 'po_amount', amountLabel: t('home.amount'), link: () => router.push('/po'), onRowClick: row => router.push(`/sc/${row.sc_id}/po/${row.po_id}`) },
      { title: t('home.pendingGrs'), rows: pendingGrs.value.slice(0, 5), idKey: 'gr_id', idLabel: t('home.grId'), amountKey: 'estimated_amount', amountLabel: t('home.estimated'), link: () => router.push('/gr'), onRowClick: row => router.push(`/sc/${row.sc_id}/po/${row.po_id}`) },
      { title: t('home.myDrafts'), rows: drafts.value.slice(0, 5), idKey: 'sc_id', idLabel: t('home.scId'), amountKey: 'sc_amount', amountLabel: t('home.amount'), link: () => router.push('/sc'), onRowClick: row => router.push(`/sc/${row.sc_id}`) }
    ]
  }
  return [
    { title: t('home.myPendingScs'), rows: pendingScs.value.slice(0, 5), idKey: 'sc_no', idLabel: t('home.scNo'), amountKey: 'sc_amount', amountLabel: t('home.amount'), link: () => router.push('/sc'), onRowClick: row => router.push(`/sc/${row.sc_id}`) },
    { title: t('home.myDrafts'), rows: drafts.value.slice(0, 5), idKey: 'sc_id', idLabel: t('home.scId'), amountKey: 'sc_amount', amountLabel: t('home.amount'), link: () => router.push('/sc'), onRowClick: row => router.push(`/sc/${row.sc_id}`) },
    { title: t('home.deniedScs'), rows: deniedScs.value.slice(0, 5), idKey: 'sc_no', idLabel: t('home.scNo'), amountKey: 'sc_amount', amountLabel: t('home.amount'), link: () => router.push('/sc'), onRowClick: row => router.push(`/sc/${row.sc_id}`) },
    { title: t('home.activePos'), rows: pendingPos.value.slice(0, 5), idKey: 'po_no', idLabel: t('home.poNo'), amountKey: 'po_amount', amountLabel: t('home.amount'), link: () => router.push('/po'), onRowClick: row => router.push(`/sc/${row.sc_id}/po/${row.po_id}`) }
  ]
})

onMounted(async () => {
  try {
    const [scResult, poResult, grResult] = await Promise.all([
      callApi('search_scs', { filters: { status: 'pending' }, limit: 5, offset: 0 }),
      callApi('search_pos', { filters: { status: 'po_pending' }, limit: 5, offset: 0 }),
      callApi('search_grs', { filters: { status: 'pending' }, limit: 5, offset: 0 })
    ])
    pendingScs.value = scResult.rows || scResult
    pendingPos.value = poResult.rows || poResult
    pendingGrs.value = grResult.rows || grResult
  } catch {}
  try {
    const draftResult = await callApi('search_scs', { filters: { status: 'draft' }, limit: 5, offset: 0 })
    drafts.value = draftResult.rows || draftResult
  } catch {}
  try {
    const deniedResult = await callApi('search_scs', { filters: { status: 'denied' }, limit: 5, offset: 0 })
    deniedScs.value = deniedResult.rows || deniedResult
  } catch {}
})
</script>

<style scoped>
.workbench-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}
</style>
