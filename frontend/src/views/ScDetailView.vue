<template>
  <div>
    <div class="detail-page-header">
      <div>
        <h2>{{ detail.sc?.sc_no || detail.sc?.sc_id || $t('sc.scDetail') }}</h2>
        <p>
          <StatusBadge v-if="detail.sc" :status="detail.sc.status" />
          <span v-if="detail.sc" style="color:#94a3b8;margin-left:8px">{{ detail.sc.request_type }}</span>
        </p>
      </div>
      <div class="header-actions">
        <el-button v-if="permissions.can_edit_sc" :disabled="loadingState.count > 0" @click="openEditDialog">{{ $t('common.edit') }}</el-button>
        <el-button v-if="permissions.can_submit_sc" type="primary" :disabled="loadingState.count > 0" @click="handleSubmit">{{ $t('common.submit') }}</el-button>
        <el-button v-if="permissions.can_confirm_sc" type="primary" :disabled="loadingState.count > 0" @click="handleConfirm">{{ $t('sc.confirm') }}</el-button>
        <el-button v-if="permissions.can_approve_sc" type="success" :disabled="loadingState.count > 0" @click="handleApprove">{{ $t('common.approve') }}</el-button>
        <el-button v-if="permissions.can_deny_sc" type="warning" :disabled="loadingState.count > 0" @click="handleDeny">{{ $t('common.deny') }}</el-button>
        <el-button v-if="permissions.can_recall_sc" type="warning" :disabled="loadingState.count > 0" @click="handleRecall">{{ $t('sc.recall') }}</el-button>
        <el-button v-if="permissions.can_delete_sc" type="danger" :disabled="loadingState.count > 0" @click="handleDelete">{{ $t('common.delete') }}</el-button>
        <el-button v-if="permissions.can_finish_sc" type="danger" :disabled="loadingState.count > 0" @click="handleFinish">{{ $t('common.finish') }}</el-button>
        <el-button v-if="permissions.can_transfer_sc" :disabled="loadingState.count > 0" @click="openTransferDialog">{{ $t('sc.transferOwner') }}</el-button>
      </div>
    </div>

    <div v-if="state.detailLoading" class="section-card">
      <el-skeleton :rows="5" animated />
    </div>

    <el-alert v-if="state.detailError" :title="state.detailError" type="error" show-icon style="margin-bottom:16px" />

    <template v-if="detail.sc">
      <div class="section-card">
        <div class="section-header">
          <h3>{{ $t('sc.scInformation') }}</h3>
          <el-button
            v-if="permissions.can_manage_po && (detail.sc?.status === 'approved' || detail.sc?.status === 'finished')"
            type="primary" size="small"
            :disabled="loadingState.count > 0"
            @click="poDialogVisible = true; poDialogMode = 'create'; poDialogRecord = null"
          >
            <el-icon><Plus /></el-icon> {{ $t('po.addPo') }}
          </el-button>
        </div>
        <ScDetailCard :sc="detail.sc" />
      </div>

      <div class="section-card">
        <ScVendorSection
          :vendors="detail.vendors || []"
          :all-vendors="vendors"
          :can-manage="permissions.can_edit_sc"
          @add="handleAddVendor"
          @remove="handleRemoveVendor"
        />
      </div>

      <div v-if="detail.sc && (detail.sc.status === 'approved' || detail.sc.status === 'finished') && detail.pos && detail.pos.length > 0" class="section-card">
        <div class="section-header">
          <h3>{{ $t('po.poRecords') }}</h3>
          <el-button size="small" @click="handleExportPos">
            <el-icon><Download /></el-icon> {{ $t('common.export') }}
          </el-button>
        </div>
        <PoTable
          :rows="detail.pos || []"
          hide-sc-info
          @row-click="row => $router.push(`/sc/${scId}/po/${row.po_id}`)"
          @detail="row => $router.push(`/sc/${scId}/po/${row.po_id}`)"
          @edit="row => { poDialogRecord = { ...row, sc_id: scId }; poDialogMode = 'edit'; poDialogVisible = true }"
          @finish="row => handlePoFinish(row)"
          @submit="row => handlePoSubmit(row)"
        />
      </div>

      <div class="section-card">
        <div class="section-header">
          <h3>{{ $t('attachment.attachments') }}</h3>
        </div>
        <AttachmentList
          entity-type="sc"
          :entity-id="detail.sc.sc_id"
          :refresh-key="attachRefreshKey"
          @changed="fetchDetail(scId)"
        />
      </div>

      <div class="section-card">
        <div class="section-header">
          <h3>{{ $t('record.record') }}</h3>
          <el-button size="small" @click="handleExportAudit">
            <el-icon><Download /></el-icon> {{ $t('common.export') }}
          </el-button>
        </div>
        <el-table :data="detail.operation_records || []" stripe border size="small">
          <el-table-column prop="created_at" :label="$t('record.created')" width="160">
            <template #default="{ row }">{{ (row.created_at || '').replace('T', ' ').slice(0, 19) || '-' }}</template>
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

    <ScFormDialog
      v-model:visible="editDialogVisible"
      mode="edit"
      :record="{ ...detail.sc, vendors: detail.vendors }"
      :users="activeUsers"
      :vendors="vendors"
      @save-submit="handleEditSave"
    />

    <PoFormDialog
      v-model:visible="poDialogVisible"
      :mode="poDialogMode"
      :record="poDialogRecord"
      :vendors="scVendors"
      :sc-record="detail.sc"
      @save="handlePoSave"
    />

    <el-dialog v-model="transferDialogVisible" :title="$t('sc.transferOwner')" width="480px">
      <p style="margin-bottom:16px;color:#5f6368">
        {{ $t('sc.transferOwnerHint', { no: detail.sc?.sc_no || detail.sc?.sc_id, old: detail.sc?.requester_id }) }}
      </p>
      <el-select v-model="selectedNewOwner" :placeholder="$t('sc.selectNewOwner')"
                 filterable style="width:100%">
        <el-option v-for="u in activeUsers"
                   :key="u.user_id" :label="`${u.user_name} (${u.user_id})`"
                   :value="u.user_id"
                   :disabled="u.user_id === detail.sc?.requester_id" />
      </el-select>
      <template #footer>
        <el-button @click="transferDialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :disabled="!selectedNewOwner" @click="handleTransferOwner">
          {{ $t('common.confirm') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Plus, Download } from '@element-plus/icons-vue'
import { useSc } from '@/composables/useSc.js'
import { usePo } from '@/composables/usePo.js'
import { useVendor } from '@/composables/useVendor.js'
import { useExport } from '@/composables/useExport.js'
import { callApi, loadingState } from '@/api/bridge.js'
import StatusBadge from '@/components/common/StatusBadge.vue'
import ScDetailCard from '@/components/sc/ScDetailCard.vue'
import ScFormDialog from '@/components/sc/ScFormDialog.vue'
import PoTable from '@/components/po/PoTable.vue'
import PoFormDialog from '@/components/po/PoFormDialog.vue'
import AttachmentList from '@/components/common/AttachmentList.vue'
import ScVendorSection from '@/components/sc/ScVendorSection.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const { state, fetchDetail, updateSc, submitSc, approveSc, denySc, finishSc } = useSc()
const { createPo, updatePo, finishPo, submitPo } = usePo()
const { state: vendorState, searchVendors } = useVendor()
const { exportRows } = useExport()

const scId = computed(() => route.params.id)
const detail = computed(() => state.detail || {})
const permissions = computed(() => detail.value.permissions || {})
const vendors = computed(() => vendorState.rows)
const scVendors = computed(() => detail.value?.vendors || [])
const activeUsers = ref([])

const editDialogVisible = ref(false)
const poDialogVisible = ref(false)
const poDialogMode = ref('create')
const poDialogRecord = ref(null)
const attachRefreshKey = ref(0)

function openEditDialog() { editDialogVisible.value = true }

async function handleEditSave(data) {
  try {
    const { _attachments, ...formData } = data
    await updateSc(formData.sc_id || scId.value, formData)
    if (_attachments?.length) {
      await callApi('add_attachments', { entity_type: 'sc', entity_id: scId.value, file_paths: _attachments })
      attachRefreshKey.value++
    }
    ElMessage.success(t('sc.scUpdated'))
    await fetchDetail(scId.value)
    editDialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
}

async function handleSubmit() {
  try {
    await ElMessageBox.confirm(t('sc.submitConfirm'), t('common.confirm'), { type: 'warning' })
    await submitSc(scId.value, {})
    ElMessage.success(t('sc.scSubmitted'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleConfirm() {
  try {
    await ElMessageBox.confirm(t('sc.confirmConfirm'), t('common.confirm'), { type: 'warning' })
    await callApi('confirm_sc', { sc_id: scId.value })
    ElMessage.success(t('sc.confirmed'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleApprove() {
  try {
    await ElMessageBox.confirm(t('sc.approveConfirm'), t('common.confirm'), { type: 'warning' })

    // Check for draft POs — offer cascade
    const draftPos = (detail.value.pos || []).filter(p => p.status === 'draft')
    let cascadePos = false
    if (draftPos.length > 0) {
      try {
        await ElMessageBox.confirm(
          `${draftPos.length} draft PO(s) exist. Also submit them?`,
          t('common.confirm'),
          { confirmButtonText: 'Yes, cascade submit', cancelButtonText: 'No, leave as draft', type: 'warning' }
        )
        cascadePos = true
      } catch { /* user chose No */ }
    }

    await approveSc(scId.value, cascadePos)
    ElMessage.success(t('sc.scApproved'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleDeny() {
  try {
    await ElMessageBox.confirm(t('sc.denyConfirm'), t('common.confirm'), { type: 'warning' })
    await denySc(scId.value)
    ElMessage.success(t('sc.scDenied'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleFinish() {
  try {
    await ElMessageBox.prompt(t('sc.finishPrompt'), t('sc.finishTitle'), {
      confirmButtonText: t('common.finish'),
      type: 'warning',
      inputPattern: /^I CONFIRM FINISH THIS SC$/,
      inputErrorMessage: t('sc.finishInputError'),
      inputPlaceholder: 'I CONFIRM FINISH THIS SC'
    })
    await finishSc(scId.value)
    ElMessage.success(t('sc.scFinished'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleRecall() {
  try {
    await ElMessageBox.confirm(t('sc.confirmRecallToDraft'), t('common.confirm'), { type: 'warning' })
    await callApi('recall_sc', { sc_id: scId.value })
    ElMessage.success(t('sc.recalled'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm(t('sc.confirmDelete'), t('common.confirm'), { type: 'error' })
    await callApi('delete_sc', { sc_id: scId.value })
    ElMessage.success(t('sc.deleted'))
    router.replace('/sc')
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handlePoFinish(row) {
  try {
    await ElMessageBox.confirm(t('po.confirmFinish'), t('common.confirm'), { type: 'warning' })
    await finishPo(row.po_id)
    ElMessage.success(t('po.finished'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handlePoSubmit(row) {
  try {
    await ElMessageBox.confirm(t('common.submit') + ' this PO?', t('common.confirm'), { type: 'warning' })
    await submitPo(row.po_id)
    ElMessage.success(t('common.submit') + ' ' + t('msg.saved'))
    await fetchDetail(scId.value)
  } catch (e) { if (e !== 'cancel') ElMessage.error(e.message || String(e)) }
}

async function handlePoSave(data) {
  try {
    const { _attachments, ...formData } = data
    let poId
    if (poDialogMode.value === 'create') {
      const created = await createPo({ ...formData, sc_id: scId.value })
      poId = created.po_id
    } else {
      poId = formData.po_id
      await updatePo(poId, formData)
    }
    if (_attachments?.length) {
      await callApi('add_attachments', { entity_type: 'po', entity_id: poId, file_paths: _attachments, parent_sc_id: scId.value })
      attachRefreshKey.value++
    }
    ElMessage.success(t('common.saved'))
    await fetchDetail(scId.value)
    poDialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
}

async function handleAddVendor(vendorIds) {
  const ids = Array.isArray(vendorIds) ? vendorIds : [vendorIds]
  try {
    for (const vendorId of ids) {
      await callApi('add_sc_vendor', { sc_id: scId.value, vendor_id: vendorId })
    }
    ElMessage.success(t('sc.vendorAdded'))
    await fetchDetail(scId.value)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function handleRemoveVendor(vendorId) {
  try {
    await ElMessageBox.confirm(
      t('sc.confirmRemoveVendor', { name: vendorId }),
      t('common.confirm'),
      { type: 'warning' }
    )
    await callApi('remove_sc_vendor', { sc_id: scId.value, vendor_id: vendorId })
    ElMessage.success(t('sc.vendorRemoved'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

const transferDialogVisible = ref(false)
const selectedNewOwner = ref('')

function openTransferDialog() {
  selectedNewOwner.value = ''
  transferDialogVisible.value = true
}

async function handleTransferOwner() {
  if (!selectedNewOwner.value) return
  try {
    await callApi('transfer_sc', {
      sc_id: scId.value,
      new_requester_id: selectedNewOwner.value,
    })
    ElMessage.success(t('sc.ownerTransferred'))
    transferDialogVisible.value = false
    await fetchDetail(scId.value)
  } catch (e) {
    ElMessage.error(e.message || String(e))
  }
}

async function handleExportPos() {
  const columns = [
    { key: 'status', label: t('po.status') },
    { key: 'po_no', label: t('po.poNo') },
    { key: 'vendor_name', label: t('po.vendor') },
    { key: 'po_amount', label: t('po.poAmount') },
    { key: 'contract_from', label: t('po.contractFrom'), getValue: r => (r.contract_from || '').slice(0, 10) },
    { key: 'contract_to', label: t('po.contractTo'), getValue: r => (r.contract_to || '').slice(0, 10) }
  ]
  const scNo = detail.value.sc?.sc_no || detail.value.sc?.sc_id || 'SC'
  await exportRows(detail.value.pos || [], columns, `${scNo}_POs`)
  ElMessage.success(t('common.exportedSuccessfully'))
}

async function handleExportAudit() {
  const columns = [
    { key: 'created_at', label: t('record.created'), getValue: r => (r.created_at || '').replace('T', ' ').slice(0, 19) },
    { key: 'action_type', label: t('record.action') },
    { key: 'object_type', label: t('record.objectType') },
    { key: 'object_id', label: t('record.objectId') },
    { key: 'operator_id', label: t('record.operator') },
    { key: 'machine_id', label: t('record.machine') }
  ]
  const scNo = detail.value.sc?.sc_no || detail.value.sc?.sc_id || 'SC'
  await exportRows(detail.value.operation_records || [], columns, `${scNo}_Records`)
  ElMessage.success(t('common.exportedSuccessfully'))
}

onMounted(async () => {
  try { activeUsers.value = await callApi('list_users') } catch {}
  await Promise.all([fetchDetail(scId.value), searchVendors()])
})

watch(() => route.params.id, async (newId) => {
  if (newId) await fetchDetail(newId)
})
</script>

<style scoped>
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.section-header h3 {
  font-size: 15px;
  font-weight: 600;
}
.header-actions {
  display: flex;
  gap: 6px;
}
</style>
