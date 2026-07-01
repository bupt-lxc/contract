<template>
  <div>
    <div class="detail-page-header">
      <div>
        <h2>{{ po.po_no || po.po_id || $t('po.poDetail') }}</h2>
        <p><StatusBadge v-if="po.status" :status="po.status" /></p>
      </div>
      <div class="header-actions">
        <el-button v-if="scDetail?.permissions?.can_manage_po && po.status !== 'finished'" :disabled="loadingState.count > 0" @click="openEditDialog">{{ $t('common.edit') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_po && po.status === 'draft'" type="primary" :disabled="loadingState.count > 0" @click="handleSubmit">{{ $t('common.submit') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_po && po.status === 'activing'" type="info" :disabled="loadingState.count > 0" @click="handleFinish">{{ $t('common.finish') }}</el-button>
        <el-button v-if="isRequester && po.status === 'activing'" type="warning" :disabled="loadingState.count > 0" @click="handleRecall">{{ $t('po.recall') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_delete_po && po.status === 'draft'" type="danger" :disabled="loadingState.count > 0" @click="handleDelete">{{ $t('common.delete') }}</el-button>
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
          <el-button v-if="scDetail?.permissions?.can_manage_gr" type="primary" size="small" :disabled="loadingState.count > 0" @click="grDialogVisible = true; grDialogMode = 'create'; grDialogRecord = null">
            <el-icon><Plus /></el-icon> {{ $t('gr.addGr') }}
          </el-button>
        </div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="$t('sc.scId')">
            <el-link type="primary" @click="$router.push(`/sc/${scDetail.sc?.sc_id}`)">{{ scDetail.sc?.sc_id }}</el-link>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('sc.scNo')">{{ scDetail.sc?.sc_no || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('sc.requester')">{{ scDetail.sc?.requester_name || scDetail.sc?.requester_id || '-' }}</el-descriptions-item>
          <el-descriptions-item />
          <el-descriptions-item :label="$t('po.poId')">{{ po.po_id }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.poNo')">{{ po.po_no || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('common.vendor')">{{ po.vendor_name || po.vendor_id }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.poAmount')"><AmountDisplay :value="po.po_amount" /></el-descriptions-item>
          <el-descriptions-item :label="$t('po.openPoAmount')"><AmountDisplay :value="po.open_po_amount" /></el-descriptions-item>
          <el-descriptions-item :label="$t('po.consumedAmount')"><AmountDisplay :value="po.consumed_amount || po.budget?.po_con_value_total" /></el-descriptions-item>
          <el-descriptions-item :label="$t('po.pendingExclTax')"><AmountDisplay :value="po.pending_total || po.budget?.po_pending_total" /></el-descriptions-item>
          <el-descriptions-item :label="$t('po.pendingInclTax')"><AmountDisplay :value="po.pending_total_incl_tax || po.budget?.po_pending_total_incl_tax" /></el-descriptions-item>
          <el-descriptions-item :label="$t('po.contractFrom')">{{ po.contract_from?.slice(0,10) || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.contractTo')">{{ po.contract_to?.slice(0,10) || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.contractNo')">{{ po.contract_no || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.paymentFreq')">{{ po.payment_frequency || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.contractPos')">{{ po.contract_pos || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.contractType')">{{ po.contract_type || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.costCenter')">{{ po.cost_center || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.purchaser')">{{ po.purchaser || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.activingDate')">{{ (po.activing_date || '').slice(0, 10) || '-' }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <div class="section-card">
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

      <div class="section-card">
        <div class="section-header">
          <h3>{{ $t('attachment.attachments') }}</h3>
        </div>
        <AttachmentList
          entity-type="po"
          :entity-id="po.po_id"
          :parent-sc-id="scId"
          :refresh-key="attachRefreshKey"
          @changed="fetchDetail(scId)"
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
    </template>

    <AttachmentDialog
      v-model:visible="grAttachVisible"
      entity-type="gr"
      :entity-id="grAttachRecord?.gr_id || ''"
      :parent-sc-id="scId"
      :parent-po-id="poId"
      @changed="fetchDetail(scId)"
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
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
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
import GrTable from '@/components/po/GrTable.vue'
import AttachmentList from '@/components/common/AttachmentList.vue'
import AttachmentDialog from '@/components/common/AttachmentDialog.vue'
import GrFormDialog from '@/components/po/GrFormDialog.vue'
import PoNotificationCard from '@/components/notification/PoNotificationCard.vue'
import PoCustomScheduleCard from '@/components/notification/PoCustomScheduleCard.vue'
import { useNotification } from '@/composables/useNotification.js'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const { state: scState, fetchDetail } = useSc()
const { updatePo, finishPo, submitPo } = usePo()
const { createGr, updateGr, approveGr, denyGr, submitGr, finishGr } = useGr()

const { state: notifState, fetchPoConfig, savePoConfig, fetchCustomSchedules, saveCustomSchedules } = useNotification()
const { exportRows } = useExport()

const scId = computed(() => route.params.scId)
const poId = computed(() => route.params.poId)
const scDetail = computed(() => scState.detail)
const po = computed(() => {
  const pos = scDetail.value?.pos || []
  return pos.find(p => String(p.po_id) === String(poId.value)) || {}
})
const grs = computed(() => {
  const allGrs = scDetail.value?.grs || []
  return allGrs.filter(g => String(g.po_id) === String(poId.value))
})
const scVendors = computed(() => scDetail.value?.vendors || [])
const isRequester = computed(() => window.__currentUser?.user_id === scDetail.value?.sc?.requester_id)
const notificationConfig = computed(() => notifState.poConfig)
const customSchedules = computed(() => notifState.customSchedules || [])

const editDialogVisible = ref(false)
const grDialogVisible = ref(false)
const grDialogMode = ref('create')
const grDialogRecord = ref(null)
const grAttachVisible = ref(false)
const grAttachRecord = ref(null)
const attachRefreshKey = ref(0)
const activeUsers = ref([])

function openEditDialog() { editDialogVisible.value = true }

async function handleEditSave(data) {
  try {
    const { _attachments, ...formData } = data
    const targetPoId = formData.po_id || poId.value
    await updatePo(targetPoId, formData)
    if (_attachments?.length) {
      await callApi('add_attachments', { entity_type: 'po', entity_id: targetPoId, file_paths: _attachments, parent_sc_id: scId.value })
      attachRefreshKey.value++
    }
    ElMessage.success(t('po.poUpdated'))
    await fetchDetail(scId.value)
    editDialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
}

async function handleFinish() {
  try {
    await ElMessageBox.confirm(t('po.finishConfirm'), t('common.confirm'), { type: 'warning' })
    await finishPo(poId.value)
    ElMessage.success(t('po.poFinished'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleRecall() {
  try {
    await ElMessageBox.confirm(t('po.confirmRecallToDraft'), t('common.confirm'), { type: 'warning' })
    await callApi('recall_po', { po_id: poId.value })
    ElMessage.success(t('po.recalled'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm(t('po.confirmDeletePo'), t('common.confirm'), { type: 'error' })
    await callApi('delete_po', { po_id: poId.value })
    ElMessage.success(t('po.poDeleted'))
    router.replace(`/sc/${scId.value}`)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleSubmit() {
  try {
    await ElMessageBox.confirm(t('common.submit') + ' this PO?', t('common.confirm'), { type: 'warning' })
    await submitPo(poId.value)
    ElMessage.success(t('common.submit') + ' ' + t('msg.saved'))
    await fetchDetail(scId.value)
  } catch (e) { if (e !== 'cancel') ElMessage.error(e.message || String(e)) }
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
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleGrDeny(row) {
  try {
    await ElMessageBox.confirm(t('gr.denyConfirm'), t('common.confirm'), { type: 'warning' })
    await denyGr(row.gr_id)
    ElMessage.success(t('gr.grDenied'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleGrSubmit(row) {
  try {
    await ElMessageBox.confirm(t('common.submit') + ' this GR?', t('common.confirm'), { type: 'warning' })
    await submitGr(row.gr_id)
    ElMessage.success(t('common.submit') + ' ' + t('msg.saved'))
    await fetchDetail(scId.value)
  } catch (e) { if (e !== 'cancel') ElMessage.error(e.message || String(e)) }
}

async function handleGrFinish(row) {
  try {
    await ElMessageBox.confirm(t('gr.finishGrConfirm'), t('gr.finishGr'), { type: 'warning' })
    await finishGr(row.gr_id)
    ElMessage.success(t('gr.grFinished'))
    await fetchDetail(scId.value)
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
    { key: 'delivery_from', label: t('gr.deliveryFrom'), getValue: r => (r.delivery_from || '').slice(0, 10) },
    { key: 'delivery_to', label: t('gr.deliveryTo'), getValue: r => (r.delivery_to || '').slice(0, 10) },
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
        payload._parent_sc_id = scId.value
        payload._parent_po_id = poId.value
      }
      const created = await createGr(payload)
      grId = created.gr_id
    } else {
      grId = formData.gr_id
      await updateGr(grId, formData)
      if (_attachments?.length) {
        await callApi('add_attachments', { entity_type: 'gr', entity_id: grId, file_paths: _attachments, parent_sc_id: scId.value, parent_po_id: poId.value })
        attachRefreshKey.value++
      }
    }
    ElMessage.success(t('common.saved'))
    await fetchDetail(scId.value)
    grDialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
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

onMounted(async () => {
  try { activeUsers.value = await callApi('list_users') } catch {}
  await fetchDetail(scId.value)
  // Fetch PO notification config once PO ID is available
  if (poId.value) {
    try { await fetchPoConfig(poId.value) } catch {}
    try { await fetchCustomSchedules(poId.value) } catch {}
  }
})
</script>
