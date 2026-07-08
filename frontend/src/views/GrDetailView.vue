<template>
  <div>
    <div class="detail-page-header">
      <div>
        <h2>{{ gr.gr_id || $t('gr.grDetail') }}</h2>
        <p><StatusBadge v-if="gr.status" :status="gr.status" /></p>
      </div>
      <div class="header-actions">
        <el-button v-if="scDetail?.permissions?.can_manage_gr && ['draft','pending','manager_confirm','approved'].includes(gr.status)" :disabled="loadingState.count > 0" @click="openEditDialog">{{ $t('common.edit') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_gr && gr.status === 'draft'" type="primary" :disabled="loadingState.count > 0" @click="handleSubmit">{{ $t('common.submit') }}</el-button>
        <el-button v-if="scDetail?.permissions?.is_admin && gr.status === 'manager_confirm'" ref="confirmBtn" type="primary" :disabled="loadingState.count > 0" @click="handleConfirm">{{ $t('gr.confirm') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_gr && gr.status === 'approved'" type="success" :disabled="loadingState.count > 0" @click="handleFinish">{{ $t('gr.finishGr') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_gr && gr.status === 'pending'" type="success" :disabled="loadingState.count > 0" @click="handleApprove">{{ $t('common.approve') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_gr && ['pending','manager_confirm'].includes(gr.status)" type="danger" :disabled="loadingState.count > 0" @click="handleDeny">{{ $t('gr.deny') }}</el-button>
        <el-button v-if="isRequester && (gr.status === 'manager_confirm' || gr.status === 'pending')" type="warning" :disabled="loadingState.count > 0" @click="handleRecall">{{ $t('gr.recall') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_delete_gr && gr.status === 'draft'" type="danger" :disabled="loadingState.count > 0" @click="handleDelete">{{ $t('common.delete') }}</el-button>
        <el-button v-if="gr.gr_id" :disabled="loadingState.count > 0" @click="handleSendEmail('gr', gr.gr_id)">
          <el-icon><Message /></el-icon> {{ $t('email.sendEmail') }}
        </el-button>
      </div>
    </div>

    <div v-if="!gr.gr_id" class="section-card">
      <el-empty :description="$t('gr.grNotFound')" />
    </div>

    <template v-if="gr.gr_id">
      <div class="section-card">
        <h3 style="margin-bottom:12px">{{ $t('gr.grInformation') }}</h3>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="$t('gr.grId')">{{ gr.gr_id }}</el-descriptions-item>
          <el-descriptions-item :label="$t('gr.grNo')">{{ gr.gr_no || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('common.status')"><StatusBadge :status="gr.status" /></el-descriptions-item>
          <el-descriptions-item :label="$t('gr.requesterId')">{{ gr.requester_name || gr.requester_id }}</el-descriptions-item>
          <el-descriptions-item :label="$t('gr.poNo')">
            <router-link :to="`/sc/${scId}/po/${gr.po_id}`">{{ po.po_no || gr.po_id }}</router-link>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('gr.scNo')">
            <router-link :to="`/sc/${scId}`">{{ scDetail?.sc?.sc_no || scId }}</router-link>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('common.vendor')">{{ po.vendor_name || po.vendor_id || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('gr.estimatedAmount')"><AmountDisplay :value="gr.estimated_amount" /></el-descriptions-item>
          <el-descriptions-item :label="$t('gr.taxRate')">{{ gr.tax_rate != null ? gr.tax_rate + '%' : '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('gr.grossCost')"><AmountDisplay :value="gr.gross_cost" /></el-descriptions-item>
          <el-descriptions-item :label="$t('gr.conValue')"><AmountDisplay :value="gr.con_value" /></el-descriptions-item>
          <el-descriptions-item :label="$t('gr.goodsServiceDescription')" :span="2">{{ gr.goods_service_description || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('gr.confirmationName')">{{ gr.confirmation_name || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('gr.lastDelivery')">{{ gr.last_delivery === 'Y' ? $t('common.yes') : $t('common.no') }}</el-descriptions-item>
          <el-descriptions-item :label="$t('gr.isCancellation')">{{ gr.is_cancellation === 'Y' ? $t('common.yes') : $t('common.no') }}</el-descriptions-item>
          <el-descriptions-item :label="$t('gr.remark')" :span="2">{{ gr.remark || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('gr.createdBy')">{{ gr.created_by || '-' }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <ProcessSummaryCard
        v-if="gr.gr_id"
        :record="gr"
        :fields="grProcessSummaryFields"
      />

      <div class="section-card">
        <div class="section-header">
          <h3>{{ $t('attachment.attachments') }}</h3>
        </div>
        <AttachmentList
          entity-type="gr"
          :entity-id="gr.gr_id"
          :parent-sc-id="scId"
          :parent-po-id="poId"
          :refresh-key="attachRefreshKey"
          @changed="fetchDetail(scId)"
        />
      </div>

      <div class="section-card">
        <div class="section-header">
          <h3>{{ $t('record.record') }}</h3>
        </div>
        <el-table :data="grOperationRecords" stripe border size="small">
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

    <GrFormDialog
      v-model:visible="editDialogVisible"
      mode="edit"
      :record="gr"
      :users="activeUsers"
      @save="handleEditSave"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useSc } from '@/composables/useSc.js'
import { useGr } from '@/composables/useGr.js'
import { callApi, loadingState } from '@/api/bridge.js'
import { formatDateTime } from '@/utils/format.js'
import { Message } from '@element-plus/icons-vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'
import AttachmentList from '@/components/common/AttachmentList.vue'
import GrFormDialog from '@/components/po/GrFormDialog.vue'
import ProcessSummaryCard from '@/components/common/ProcessSummaryCard.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const { state: scState, fetchDetail } = useSc()
const { updateGr, approveGr, denyGr, finishGr, submitGr } = useGr()

const scId = computed(() => route.params.scId)
const poId = computed(() => route.params.poId)
const grId = computed(() => route.params.grId)
const scDetail = computed(() => scState.detail)

const po = computed(() => {
  const pos = scDetail.value?.pos || []
  return pos.find(p => String(p.po_id) === String(poId.value)) || {}
})
const gr = computed(() => {
  const allGrs = scDetail.value?.grs || []
  return allGrs.find(g => String(g.gr_id) === String(grId.value)) || {}
})
const grOperationRecords = computed(() => {
  const logs = scDetail.value?.operation_records || []
  return logs.filter(l => l.object_type === 'gr' && l.object_id === grId.value)
})
const isRequester = computed(() => window.__currentUser?.user_id === scDetail.value?.sc?.requester_id)

const grProcessSummaryFields = computed(() => [
  { key: 'created_at', label: t('timestampLabel.created') },
  { key: 'submitted_date', label: t('timestampLabel.submitted') },
  { key: 'confirmed_at', label: t('timestampLabel.confirmed') },
  { key: 'pending_date', label: t('timestampLabel.pending') },
  { key: 'approved_date', label: t('timestampLabel.approved') },
  { key: 'finished_at', label: t('timestampLabel.finished') },
  { key: 'updated_at', label: t('timestampLabel.updated') }
])

const confirmBtn = ref(null)
const editDialogVisible = ref(false)
const attachRefreshKey = ref(0)
const activeUsers = ref([])

function openEditDialog() { editDialogVisible.value = true }

async function handleSubmit() {
  try {
    await ElMessageBox.confirm(t('gr.confirmSubmit'), t('common.confirm'), { type: 'warning' })
    await submitGr(grId.value)
    ElMessage.success(t('gr.grSubmitted'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleEditSave(data) {
  try {
    const { _attachments, ...formData } = data
    await updateGr(formData.gr_id || grId.value, formData)
    if (_attachments?.length) {
      await callApi('add_attachments', { entity_type: 'gr', entity_id: grId.value, file_paths: _attachments, parent_sc_id: scId.value, parent_po_id: poId.value })
      attachRefreshKey.value++
    }
    ElMessage.success(t('common.saved'))
    await fetchDetail(scId.value)
    editDialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
}

async function handleConfirm() {
  try {
    await ElMessageBox.confirm(t('gr.confirmConfirm'), t('common.confirm'), { type: 'warning' })
    await callApi('confirm_gr', { gr_id: grId.value })
    ElMessage.success(t('gr.confirmed'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleApprove() {
  try {
    // Pre-fill with gross_cost (tax-included amount) when available
    const grData = gr.value || {}
    let defaultVal = String(grData.gross_cost || grData.con_value || '')
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
    await approveGr(grId.value, conValue)
    ElMessage.success(t('gr.grApproved'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleDeny() {
  try {
    await ElMessageBox.confirm(t('gr.denyConfirm'), t('common.confirm'), { type: 'warning' })
    await denyGr(grId.value)
    ElMessage.success(t('gr.grDenied'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleFinish() {
  try {
    await ElMessageBox.confirm(t('gr.finishGrConfirm'), t('gr.finishGr'), { type: 'warning' })
    const result = await finishGr(grId.value, false)

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
      await finishGr(grId.value, true)
      ElMessage.success(t('gr.grAndPoFinished'))
    } else {
      ElMessage.success(t('gr.grFinished'))
    }
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleRecall() {
  try {
    await ElMessageBox.confirm(t('gr.confirmRecallToDraft'), t('common.confirm'), { type: 'warning' })
    await callApi('recall_gr', { gr_id: grId.value })
    ElMessage.success(t('gr.recalled'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleSendEmail(entityType, entityId) {
  try {
    await callApi('open_entity_email', { entity_type: entityType, entity_id: entityId })
  } catch (e) {
    ElMessage.error(e.message || String(e))
  }
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm(t('gr.confirmDeleteGr'), t('common.confirm'), { type: 'error' })
    await callApi('delete_gr', { gr_id: grId.value })
    ElMessage.success(t('gr.grDeleted'))
    router.replace(`/sc/${scId.value}/po/${poId.value}`)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

onMounted(async () => {
  try { activeUsers.value = await callApi('list_users') } catch {}
  await fetchDetail(scId.value)

  if (window.__pendingConfirmAction?.type === 'gr' && window.__pendingConfirmAction?.id === grId.value) {
    window.__pendingConfirmAction = null
    setTimeout(() => {
      confirmBtn.value?.$el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      confirmBtn.value?.$el?.classList.add('confirm-pulse')
      setTimeout(() => confirmBtn.value?.$el?.classList.remove('confirm-pulse'), 3000)
    }, 500)
  }
})
</script>

<style scoped>
.confirm-pulse {
  animation: pulse 0.6s ease-in-out 3;
  box-shadow: 0 0 0 0 rgba(52, 168, 83, 0.6);
}
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(52, 168, 83, 0.6); }
  50% { box-shadow: 0 0 0 8px rgba(52, 168, 83, 0); }
  100% { box-shadow: 0 0 0 0 rgba(52, 168, 83, 0); }
}
</style>
