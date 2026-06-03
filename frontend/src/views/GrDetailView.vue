<template>
  <div>
    <div class="detail-page-header">
      <div>
        <h2>{{ gr.gr_id || $t('gr.grDetail') }}</h2>
        <p><StatusBadge v-if="gr.status" :status="gr.status" /></p>
      </div>
      <div class="header-actions">
        <el-button v-if="scDetail?.permissions?.can_manage_gr && (gr.status === 'pending' || gr.status === 'manager_confirm')" @click="openEditDialog">{{ $t('common.edit') }}</el-button>
        <el-button v-if="scDetail?.permissions?.is_admin && gr.status === 'manager_confirm'" type="primary" @click="handleConfirm">{{ $t('gr.confirm') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_gr && gr.status === 'pending'" type="success" @click="handleApprove">{{ $t('common.approve') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_gr && gr.status === 'pending'" type="danger" @click="handleCancel">{{ $t('gr.cancel') }}</el-button>
        <el-button v-if="scDetail?.permissions?.is_admin && (gr.status === 'approved' || gr.status === 'cancelled' || gr.status === 'pending')" type="warning" @click="handleRevoke">{{ $t('gr.revoke') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_delete_gr && (gr.status === 'manager_confirm' || gr.status === 'pending' || gr.status === 'cancelled')" type="danger" @click="handleDelete">{{ $t('common.delete') }}</el-button>
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
          <el-descriptions-item :label="$t('gr.requesterId')">{{ gr.requester_id }}</el-descriptions-item>
          <el-descriptions-item :label="$t('gr.poNo')">
            <router-link :to="`/sc/${scId}/po/${gr.po_id}`">{{ po.po_no || gr.po_id }}</router-link>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('gr.scNo')">
            <router-link :to="`/sc/${scId}`">{{ scDetail?.sc?.sc_no || scId }}</router-link>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('common.vendor')">{{ po.vendor_name || po.vendor_id || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('gr.estimatedAmount')"><AmountDisplay :value="gr.estimated_amount" /></el-descriptions-item>
          <el-descriptions-item :label="$t('gr.taxRate')">{{ gr.tax_rate != null ? gr.tax_rate + '%' : '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('gr.conValue')"><AmountDisplay :value="gr.con_value" /></el-descriptions-item>
          <el-descriptions-item :label="$t('gr.remark')" :span="2">{{ gr.remark || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('gr.confirmedAt')">{{ (gr.confirmed_at || '').slice(0, 10) || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('gr.pendingDate')">{{ (gr.pending_date || '').slice(0, 10) || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('gr.approvedDate')">{{ (gr.approved_date || '').slice(0, 10) || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('gr.created')">{{ gr.created_at?.slice(0, 19) || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('gr.createdBy')">{{ gr.created_by || '-' }}</el-descriptions-item>
        </el-descriptions>
      </div>

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
          <h3>{{ $t('audit.audit') }}</h3>
        </div>
        <el-table :data="grAuditLogs" stripe border size="small">
          <el-table-column prop="created_at" :label="$t('audit.created')" width="160">
            <template #default="{ row }">{{ row.created_at?.slice(0, 19) }}</template>
          </el-table-column>
          <el-table-column prop="action_type" :label="$t('audit.action')" width="140" />
          <el-table-column prop="object_type" :label="$t('audit.object')" width="100" />
          <el-table-column prop="object_id" :label="$t('audit.objectId')" width="120" />
          <el-table-column prop="operator_id" :label="$t('audit.operator')" width="120" />
          <el-table-column prop="changes_summary" :label="$t('audit.changes')" min-width="220" />
          <template #empty><el-empty :description="$t('audit.noRecordsInSc')" /></template>
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
import { callApi } from '@/api/bridge.js'
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'
import AttachmentList from '@/components/common/AttachmentList.vue'
import GrFormDialog from '@/components/po/GrFormDialog.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const { state: scState, fetchDetail } = useSc()
const { updateGr, approveGr, cancelGr } = useGr()

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
const grAuditLogs = computed(() => {
  const logs = scDetail.value?.audit_logs || []
  return logs.filter(l => l.object_type === 'gr' && l.object_id === grId.value)
})

const editDialogVisible = ref(false)
const attachRefreshKey = ref(0)
const activeUsers = ref([])

function openEditDialog() { editDialogVisible.value = true }

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
    // Pre-fill with auto-calculated tax-included amount if tax_rate is set
    const grData = gr.value || {}
    let defaultVal = ''
    if (grData.estimated_amount && grData.tax_rate != null) {
      defaultVal = String(Math.round((Number(grData.estimated_amount) * (1 + Number(grData.tax_rate) / 100)) * 100) / 100)
    }
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

async function handleCancel() {
  try {
    await ElMessageBox.confirm(t('gr.cancelConfirm'), t('common.confirm'), { type: 'warning' })
    await cancelGr(grId.value)
    ElMessage.success(t('gr.grCancelled'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleRevoke() {
  try {
    const confirmMsg = gr.value.status === 'pending' ? t('gr.confirmRevokePending') : t('gr.confirmRevoke')
    await ElMessageBox.confirm(confirmMsg, t('common.confirm'), { type: 'warning' })
    await callApi('revoke_gr', { gr_id: grId.value })
    ElMessage.success(t('gr.revoked'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
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
})
</script>
