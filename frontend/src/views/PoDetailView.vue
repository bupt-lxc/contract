<template>
  <div>
    <div class="detail-page-header">
      <div>
        <h2>{{ po.po_no || po.po_id || $t('po.poDetail') }}</h2>
        <p><StatusBadge v-if="po.status" :status="po.status" /></p>
      </div>
      <div class="header-actions">
        <el-button v-if="permissions?.can_manage_po && po.status !== 'finished'" :disabled="loadingState.count > 0" @click="openEditDialog">{{ $t('common.edit') }}</el-button>
        <el-button v-if="permissions?.can_manage_po && po.status === 'draft'" type="primary" :disabled="loadingState.count > 0" @click="handleSubmit">{{ $t('common.submit') }}</el-button>
        <el-button v-if="permissions?.can_manage_po && po.status === 'active'" type="info" :disabled="loadingState.count > 0" @click="handleFinish">{{ $t('common.finish') }}</el-button>
        <el-button v-if="isRequester && po.status === 'active'" type="warning" :disabled="loadingState.count > 0" @click="handleRecall">{{ $t('po.recall') }}</el-button>
        <el-button v-if="permissions?.can_delete_po && po.status === 'draft'" type="danger" :disabled="loadingState.count > 0" @click="handleDelete">{{ $t('common.delete') }}</el-button>
        <el-button v-if="po.po_id" :disabled="loadingState.count > 0" @click="handleSendEmail('po', po.po_id)">
          <el-icon><Message /></el-icon> {{ $t('email.sendEmail') }}
        </el-button>
      </div>
    </div>

    <div v-if="!po.po_id" class="section-card">
      <el-empty :description="$t('po.poNotFound')" />
    </div>

    <template v-if="po.po_id">
      <div class="section-card">
        <div class="section-header">
          <h3>{{ $t('po.poInformation') }}</h3>
          <el-button v-if="permissions?.can_manage_gr && !isFcPo && po.status !== 'finished'" type="primary" size="small" :disabled="loadingState.count > 0" @click="grDialogVisible = true; grDialogMode = 'create'; grDialogRecord = null">
            <el-icon><Plus /></el-icon> {{ $t('gr.addGr') }}
          </el-button>
          <el-button v-if="permissions?.can_manage_po && isFcPo" type="primary" size="small" :disabled="loadingState.count > 0" @click="openCalloffScDialog">
            <el-icon><Plus /></el-icon> {{ $t('po.newCalloffSc') }}
          </el-button>
        </div>
        <el-descriptions :column="2" border size="small">
          <template v-if="hasSc">
            <el-descriptions-item :label="$t('sc.scId')">
              <el-link type="primary" @click="$router.push(`/sc/${scDetail.sc?.sc_id}`)">{{ scDetail.sc?.sc_id }}</el-link>
            </el-descriptions-item>
            <el-descriptions-item :label="$t('sc.scNo')">{{ scDetail.sc?.sc_no || '-' }}</el-descriptions-item>
            <el-descriptions-item :label="$t('sc.requester')">{{ scDetail.sc?.requester_name || scDetail.sc?.requester_id || '-' }}</el-descriptions-item>
            <el-descriptions-item />
          </template>
          <el-descriptions-item :label="$t('po.poId')">{{ po.po_id }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.poNo')">{{ po.po_no || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('common.vendor')">{{ po.vendor_name || po.vendor_id }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.poAmount')"><AmountDisplay :value="po.po_amount" /></el-descriptions-item>
          <el-descriptions-item :label="$t('po.openPoAmount')"><AmountDisplay :value="po.open_po_amount" /></el-descriptions-item>
          <el-descriptions-item :label="$t('po.contractFrom')">{{ po.contract_from?.slice(0,10) || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.contractTo')">{{ po.contract_to?.slice(0,10) || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.contractNo')">{{ po.contract_no || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.paymentFreq')">{{ po.payment_frequency || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.contractPos')">{{ po.contract_pos || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.contractType')">{{ po.contract_type || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.costCenter')">{{ po.cost_center || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.purchaser')">{{ po.purchaser || '-' }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <PoBudgetCard
        v-if="po.po_id"
        :budget="poBudget"
        :is-fc-po="isFcPo"
      />

      <ProcessSummaryCard
        v-if="po.po_id"
        :record="po"
        :fields="poProcessSummaryFields"
      />

      <div v-if="hasSc && !isFcPo" class="section-card">
        <div class="section-header">
          <h3>{{ $t('gr.grRecords') }}</h3>
          <el-button size="small" @click="handleExportGrs">
            <el-icon><Download /></el-icon> {{ $t('common.export') }}
          </el-button>
        </div>
        <GrTable
          :rows="grs"
          @row-click="row => $router.push(`/sc/${scId}/po/${poId}/gr/${row.gr_id}`)"
          @detail="row => $router.push(`/sc/${scId}/po/${poId}/gr/${row.gr_id}`)"
          @edit="row => { grDialogRecord = { ...row, po_id: poId }; grDialogMode = 'edit'; grDialogVisible = true }"
          @approve="row => handleGrApprove(row)"
          @deny="row => handleGrDeny(row)"
          @finish="row => handleGrFinish(row)"
          @submit="row => handleGrSubmit(row)"
          @attachments="row => { grAttachRecord = row; grAttachVisible = true }"
        />
      </div>

      <div v-if="isFcPo" class="section-card">
        <div class="section-header">
          <h3>{{ $t('sc.calloffBadge') }}</h3>
          <el-button v-if="permissions?.can_manage_po" type="primary" size="small" :disabled="loadingState.count > 0" @click="openCalloffScDialog">
            <el-icon><Plus /></el-icon> {{ $t('po.newCalloffSc') }}
          </el-button>
        </div>
        <el-table :data="calloffScs" stripe border size="small" @row-click="row => $router.push(`/sc/${row.sc_id}`)">
          <el-table-column prop="sc_id" :label="$t('sc.scId')" />
          <el-table-column prop="sc_no" :label="$t('sc.scNo')" />
          <el-table-column prop="request_type" :label="$t('sc.requestType')" />
          <el-table-column :label="$t('sc.scAmount')">
            <template #default="{ row }"><AmountDisplay :value="row.sc_amount" /></template>
          </el-table-column>
          <el-table-column prop="status" :label="$t('sc.status')">
            <template #default="{ row }"><StatusBadge :status="row.status" /></template>
          </el-table-column>
          <template #empty><el-empty :description="$t('sc.noRecords')" /></template>
        </el-table>
      </div>

      <div class="section-card">
        <div class="section-header">
          <h3>{{ $t('attachment.attachments') }}</h3>
        </div>
        <AttachmentList
          entity-type="po"
          :entity-id="po.po_id"
          :parent-sc-id="hasSc ? scId : null"
          :refresh-key="attachRefreshKey"
          @changed="refreshDetail"
        />
      </div>

      <PoNotificationCard
        v-if="po.po_id"
        :po-id="po.po_id"
        :config="notificationConfig"
        :users="activeUsers"
        @save="handleNotificationSave"
      />

      <PoCustomScheduleCard
        v-if="po.po_id"
        :po-id="po.po_id"
        :schedules="customSchedules"
        @save="handleCustomSchedulesSave"
      />

      <div class="section-card">
        <div class="section-header">
          <h3>{{ $t('record.record') }}</h3>
        </div>
        <el-table :data="poOperationRecords" stripe border size="small">
          <el-table-column prop="created_at" :label="$t('record.created')" width="160">
            <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column prop="action_type" :label="$t('record.action')" width="140" />
          <el-table-column prop="object_type" :label="$t('record.object')" width="100" />
          <el-table-column prop="object_id" :label="$t('record.objectId')" width="120" />
          <el-table-column prop="operator_id" :label="$t('record.operator')" width="120" />
          <el-table-column prop="changes_summary" :label="$t('record.changes')" min-width="220" />
          <template #empty><el-empty :description="$t('record.noRecordsInSc')" /></template>
        </el-table>
      </div>
    </template>

    <AttachmentDialog
      v-model:visible="grAttachVisible"
      entity-type="gr"
      :entity-id="grAttachRecord?.gr_id || ''"
      :parent-sc-id="hasSc ? scId : null"
      :parent-po-id="poId"
      @changed="refreshDetail"
    />

    <PoFormDialog
      v-model:visible="editDialogVisible"
      mode="edit"
      :record="po"
      :vendors="scVendors"
      @save="handleEditSave"
    />

    <GrFormDialog
      v-model:visible="grDialogVisible"
      :mode="grDialogMode"
      :record="grDialogRecord"
      :users="activeUsers"
      @save="handleGrSave"
      @save-draft="handleGrSaveDraft"
    />

    <ScFormDialog
      v-model:visible="scDialogVisible"
      mode="create"
      :record="scDialogRecord"
      :users="activeUsers"
      :vendors="vendors"
      :calloff-po-id="po.po_id"
      :calloff-po-info="{ po_id: po.po_id, open_po_amount: po.open_po_amount }"
      @save-submit="handleCalloffScSave"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { Plus, Download, Message } from '@element-plus/icons-vue'
import { callApi, loadingState } from '@/api/bridge.js'
import { useSc } from '@/composables/useSc.js'
import { useExport } from '@/composables/useExport.js'
import { usePo } from '@/composables/usePo.js'
import { useGr } from '@/composables/useGr.js'

import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'
import PoFormDialog from '@/components/po/PoFormDialog.vue'
import PoBudgetCard from '@/components/po/PoBudgetCard.vue'
import ProcessSummaryCard from '@/components/common/ProcessSummaryCard.vue'
import GrTable from '@/components/po/GrTable.vue'
import AttachmentList from '@/components/common/AttachmentList.vue'
import AttachmentDialog from '@/components/common/AttachmentDialog.vue'
import GrFormDialog from '@/components/po/GrFormDialog.vue'
import ScFormDialog from '@/components/sc/ScFormDialog.vue'
import PoNotificationCard from '@/components/notification/PoNotificationCard.vue'
import PoCustomScheduleCard from '@/components/notification/PoCustomScheduleCard.vue'
import { useNotification } from '@/composables/useNotification.js'
import { useVendor } from '@/composables/useVendor.js'
import { formatDateTime } from '@/utils/format.js'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const { state: scState, fetchDetail } = useSc()
const { updatePo, finishPo, submitPo } = usePo()
const { createGr, updateGr, approveGr, denyGr, submitGr, finishGr } = useGr()

const { state: notifState, fetchPoConfig, savePoConfig, fetchCustomSchedules, saveCustomSchedules } = useNotification()
const { state: vendorState, searchVendors } = useVendor()
const { exportRows } = useExport()

const scId = computed(() => route.params.scId)
const poId = computed(() => route.params.poId)
const hasSc = computed(() => !!route.params.scId)
const scDetail = computed(() => scState.detail)
const poDetail = ref(null)
const po = computed(() => {
  if (hasSc.value) {
    const pos = scDetail.value?.pos || []
    return pos.find(p => String(p.po_id) === String(poId.value)) || {}
  }
  return poDetail.value?.po || {}
})
const isFcPo = computed(() => po.value?.sc_request_type === 'FC')
const grs = computed(() => {
  if (hasSc.value) {
    const allGrs = scDetail.value?.grs || []
    return allGrs.filter(g => String(g.po_id) === String(poId.value))
  }
  return []
})
const scVendors = computed(() => scDetail.value?.vendors || [])
const vendors = computed(() => vendorState.rows)
const poOperationRecords = computed(() => {
  if (hasSc.value) {
    const logs = scDetail.value?.operation_records || []
    return logs.filter(l => l.object_type === 'po' && l.object_id === poId.value)
  }
  return poDetail.value?.operation_records || []
})
const permissions = computed(() => {
  if (hasSc.value) {
    return scDetail.value?.permissions || {}
  }
  return poDetail.value?.permissions || {}
})
const isRequester = computed(() => window.__currentUser?.user_id === scDetail.value?.sc?.requester_id)
const notificationConfig = computed(() => notifState.poConfig)
const customSchedules = computed(() => notifState.customSchedules || [])

const poBudget = computed(() => ({
  po_amount: po.value.po_amount,
  open_po_amount: po.value.open_po_amount,
  allocated_calloff_amount: po.value.allocated_calloff_amount,
  pending_calloff_amount: po.value.pending_calloff_amount,
  downstream_consumed: po.value.downstream_consumed,
  downstream_pending_gr: po.value.downstream_pending_gr,
  downstream_pending_gr_tax: po.value.downstream_pending_gr_tax,
  consumed_amount: po.value.consumed_amount,
  pending_total: po.value.pending_total,
  pending_total_incl_tax: po.value.pending_total_incl_tax,
  po_con_value_total: po.value.budget?.po_con_value_total,
  po_pending_total: po.value.budget?.po_pending_total,
  po_pending_total_incl_tax: po.value.budget?.po_pending_total_incl_tax
}))

const poProcessSummaryFields = computed(() => [
  { key: 'created_at', label: t('timestampLabel.created') },
  { key: 'active_date', label: t('timestampLabel.active') },
  { key: 'finished_at', label: t('timestampLabel.finished') },
  { key: 'updated_at', label: t('timestampLabel.updated') }
])

const editDialogVisible = ref(false)
const scDialogVisible = ref(false)
const scDialogRecord = ref(null)
const grDialogVisible = ref(false)
const grDialogMode = ref('create')
const grDialogRecord = ref(null)
const grAttachVisible = ref(false)
const grAttachRecord = ref(null)
const attachRefreshKey = ref(0)
const activeUsers = ref([])
const calloffScsData = ref([])
const calloffScs = computed(() => {
  if (hasSc.value) return calloffScsData.value
  return poDetail.value?.calloff_scs || []
})

async function loadCalloffData() {
  if (!isFcPo.value) return
  try {
    const result = await callApi('search_scs', { filters: { calloff_po_id: po.value.po_id } })
    calloffScsData.value = result.rows || []
  } catch { calloffScsData.value = [] }
}

function openEditDialog() { editDialogVisible.value = true }

async function handleEditSave(data) {
  try {
    const { _attachments, ...formData } = data
    const targetPoId = formData.po_id || poId.value
    await updatePo(targetPoId, formData)
    if (_attachments?.length) {
      await callApi('add_attachments', { entity_type: 'po', entity_id: targetPoId, file_paths: _attachments, parent_sc_id: hasSc.value ? scId.value : null })
      attachRefreshKey.value++
    }
    ElMessage.success(t('po.poUpdated'))
    await refreshDetail()
    editDialogVisible.value = false
  } catch (e) { ElMessage.error(e.message || String(e)) }
}

async function handleFinish() {
  try {
    await ElMessageBox.confirm(t('po.finishConfirm'), t('common.confirm'), { type: 'warning' })
    await finishPo(poId.value)
    ElMessage.success(t('po.poFinished'))
    await refreshDetail()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleRecall() {
  try {
    await ElMessageBox.confirm(t('po.confirmRecallToDraft'), t('common.confirm'), { type: 'warning' })
    await callApi('recall_po', { po_id: poId.value })
    ElMessage.success(t('po.recalled'))
    await refreshDetail()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm(t('po.confirmDeletePo'), t('common.confirm'), { type: 'error' })
    await callApi('delete_po', { po_id: poId.value })
    ElMessage.success(t('po.poDeleted'))
    if (hasSc.value) {
      router.replace(`/sc/${scId.value}`)
    } else {
      router.replace('/po')
    }
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleSubmit() {
  try {
    await ElMessageBox.confirm(t('common.submit') + ' this PO?', t('common.confirm'), { type: 'warning' })
    await submitPo(poId.value)
    ElMessage.success(t('common.submit') + ' ' + t('msg.saved'))
    await refreshDetail()
  } catch (e) { if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e)) }
}

function openCalloffScDialog() {
  scDialogRecord.value = { sc_id: null }
  scDialogVisible.value = true
}

async function handleCalloffScSave(data) {
  try {
    const { _attachments, ...formData } = data
    const result = await callApi('create_sc_draft', formData)
    if (_attachments?.length) {
      await callApi('add_attachments', { entity_type: 'sc', entity_id: result.sc_id, file_paths: _attachments })
    }
    ElMessage.success(t('common.saved'))
    scDialogVisible.value = false
    await refreshDetail()
    await loadCalloffData()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleGrApprove(row) {
  try {
    // Pre-fill with gross_cost (tax-included amount) when available
    let defaultVal = String(row.gross_cost || row.con_value || '')
    const { value } = await ElMessageBox.prompt(
      t('gr.enterConValue'),
      t('gr.approveGr'),
      {
        confirmButtonText: t('common.approve'),
        type: 'warning',
        inputValue: defaultVal,
        inputPattern: /^(\d+(\.\d{1,2})?)?$/,
        inputErrorMessage: t('gr.invalidNumber')
      }
    )
    const conValue = value ? parseFloat(value) : null
    await approveGr(row.gr_id, conValue)
    ElMessage.success(t('gr.grApproved'))
    await refreshDetail()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleGrDeny(row) {
  try {
    await ElMessageBox.confirm(t('gr.denyConfirm'), t('common.confirm'), { type: 'warning' })
    await denyGr(row.gr_id)
    ElMessage.success(t('gr.grDenied'))
    await refreshDetail()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleGrSubmit(row) {
  try {
    await ElMessageBox.confirm(t('common.submit') + ' this GR?', t('common.confirm'), { type: 'warning' })
    await submitGr(row.gr_id)
    ElMessage.success(t('common.submit') + ' ' + t('msg.saved'))
    await refreshDetail()
  } catch (e) { if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e)) }
}

async function handleGrFinish(row) {
  try {
    await ElMessageBox.confirm(t('gr.finishGrConfirm'), t('gr.finishGr'), { type: 'warning' })
    const result = await finishGr(row.gr_id, false)

    if (result.needs_cascade) {
      const grsToFinish = result.grs_to_finish || []
      const message = grsToFinish.length > 0
        ? t('gr.lastDeliveryCascadeMessage', { list: grsToFinish.join(', ') })
        : t('gr.lastDeliveryNoCascadeMessage')
      await ElMessageBox.confirm(message, t('gr.lastDeliveryCascadeTitle'), {
        type: 'warning',
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
      })
      await finishGr(row.gr_id, true)
      ElMessage.success(t('gr.grAndPoFinished'))
    } else {
      ElMessage.success(t('gr.grFinished'))
    }
    await refreshDetail()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleExportGrs() {
  const columns = [
    { key: 'status', label: t('common.status') },
    { key: 'gr_id', label: t('gr.grId') },
    { key: 'requester_id', label: t('gr.requester') },
    { key: 'estimated_amount', label: t('gr.estimated') },
    { key: 'tax_rate', label: t('gr.taxRate') },
    { key: 'con_value', label: t('gr.conValue') },
    { key: 'goods_service_description', label: t('gr.goodsServiceDescription') },
    { key: 'confirmation_name', label: t('gr.confirmationName') },
    { key: 'last_delivery', label: t('gr.lastDelivery') },
    { key: 'remark', label: t('common.remark') }
  ]
  const poNo = po.value?.po_no || po.value?.po_id || 'PO'
  await exportRows(grs.value, columns, `${poNo}_GRs`)
  ElMessage.success(t('common.exportedSuccessfully'))
}

async function handleSendEmail(entityType, entityId) {
  try {
    await callApi('open_entity_email', { entity_type: entityType, entity_id: entityId })
  } catch (e) {
    ElMessage.error(e.message || String(e))
  }
}

async function handleGrSave(data) {
  try {
    const { _attachments, ...formData } = data
    let grId
    if (grDialogMode.value === 'create') {
      const payload = { ...formData, po_id: poId.value }
      if (po.value?.status !== 'draft') {
        payload.status = 'manager_confirm'
      }
      if (_attachments?.length) {
        payload._attachments = _attachments
        payload._parent_sc_id = hasSc.value ? scId.value : null
        payload._parent_po_id = poId.value
      }
      const created = await createGr(payload)
      grId = created.gr_id
    } else {
      grId = formData.gr_id
      await updateGr(grId, formData)
      if (_attachments?.length) {
        await callApi('add_attachments', { entity_type: 'gr', entity_id: grId, file_paths: _attachments, parent_sc_id: hasSc.value ? scId.value : null, parent_po_id: poId.value })
        attachRefreshKey.value++
      }
    }
    ElMessage.success(t('common.saved'))
    await refreshDetail()
    grDialogVisible.value = false
  } catch (e) { ElMessage.error(e.message || String(e)) }
}

async function handleGrSaveDraft(data) {
  try {
    const { _attachments, ...formData } = data
    const payload = { ...formData, po_id: poId.value, status: 'draft' }
    if (_attachments?.length) {
      payload._attachments = _attachments
      payload._parent_sc_id = hasSc.value ? scId.value : null
      payload._parent_po_id = poId.value
    }
    const created = await createGr(payload)
    if (_attachments?.length) {
      await callApi('add_attachments', { entity_type: 'gr', entity_id: created.gr_id, file_paths: _attachments, parent_sc_id: hasSc.value ? scId.value : null, parent_po_id: poId.value })
      attachRefreshKey.value++
    }
    ElMessage.success(t('po.draftSaved'))
    await refreshDetail()
    grDialogVisible.value = false
  } catch (e) { ElMessage.error(e.message || String(e)) }
}

async function handleNotificationSave(data) {
  try {
    await savePoConfig(poId.value, data)
    ElMessage.success(t('notification.settingsSaved'))
  } catch (e) {
    ElMessage.error(e.message || t('notification.saveFailed'))
  }
}

async function handleCustomSchedulesSave(schedules) {
  try {
    await saveCustomSchedules(poId.value, schedules)
    ElMessage.success(t('notification.scheduleSaved'))
  } catch (e) {
    ElMessage.error(e.message || t('notification.saveFailed'))
  }
}

async function refreshDetail() {
  if (hasSc.value) {
    await fetchDetail(scId.value)
  } else {
    try {
      const result = await callApi('get_po_detail', { po_id: poId.value })
      poDetail.value = result
    } catch (e) {
      ElMessage.error(e.message || 'Failed to refresh PO detail')
    }
  }
}

let isMounted = false

// Re-fetch data when navigating between POs on the same route pattern
watch(
  () => [route.params.scId, route.params.poId],
  async ([newScId, newPoId], [oldScId, oldPoId]) => {
    if (!isMounted) return
    if (newScId === oldScId && newPoId === oldPoId) return
    await refreshDetail()
    if (hasSc.value) {
      await loadCalloffData()
      if (newPoId) {
        try { await fetchPoConfig(newPoId) } catch {}
        try { await fetchCustomSchedules(newPoId) } catch {}
      }
    } else {
      if (newPoId) {
        try { await fetchPoConfig(newPoId) } catch {}
        try { await fetchCustomSchedules(newPoId) } catch {}
      }
    }
  }
)

onUnmounted(() => {
  isMounted = false
})

onMounted(async () => {
  isMounted = true
  try { activeUsers.value = await callApi('list_users') } catch {}
  await searchVendors()

  if (hasSc.value) {
    await fetchDetail(scId.value)
    await loadCalloffData()
    if (poId.value) {
      try { await fetchPoConfig(poId.value) } catch {}
      try { await fetchCustomSchedules(poId.value) } catch {}
    }
  } else {
    try {
      const result = await callApi('get_po_detail', { po_id: poId.value })
      poDetail.value = result
    } catch (e) {
      ElMessage.error(e.message || 'Failed to load PO detail')
    }
    if (poId.value) {
      try { await fetchPoConfig(poId.value) } catch {}
      try { await fetchCustomSchedules(poId.value) } catch {}
    }
  }
})
</script>
