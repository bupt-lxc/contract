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
        <el-button v-if="permissions.can_edit_sc" @click="openEditDialog">{{ $t('common.edit') }}</el-button>
        <el-button v-if="permissions.can_submit_sc" type="primary" @click="handleSubmit">{{ $t('common.submit') }}</el-button>
        <el-button v-if="permissions.can_confirm_sc" type="primary" @click="handleConfirm">{{ $t('sc.confirm') }}</el-button>
        <el-button v-if="permissions.can_approve_sc" type="success" @click="handleApprove">{{ $t('common.approve') }}</el-button>
        <el-button v-if="permissions.can_deny_sc" type="warning" @click="handleDeny">{{ $t('common.deny') }}</el-button>
        <el-button v-if="permissions.can_revoke_sc" type="warning" @click="handleRevoke">{{ $t('sc.revoke') }}</el-button>
        <el-button v-if="permissions.can_delete_sc" type="danger" @click="handleDelete">{{ $t('common.delete') }}</el-button>
        <el-button v-if="permissions.can_close_sc" type="danger" @click="handleClose">{{ $t('common.close') }}</el-button>
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
            v-if="permissions.can_manage_po && (detail.sc?.status === 'approved' || detail.sc?.status === 'closed')"
            type="primary" size="small"
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

      <div v-if="detail.sc && (detail.sc.status === 'approved' || detail.sc.status === 'closed')" class="section-card">
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
          <h3>{{ $t('audit.audit') }}</h3>
          <el-button size="small" @click="handleExportAudit">
            <el-icon><Download /></el-icon> {{ $t('common.export') }}
          </el-button>
        </div>
        <el-table :data="detail.audit_logs || []" stripe border size="small">
          <el-table-column prop="created_at" :label="$t('audit.created')" width="160">
            <template #default="{ row }">{{ row.created_at?.slice(0,19) }}</template>
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
      :vendors="vendors"
      @save="handlePoSave"
    />
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
import { callApi } from '@/api/bridge.js'
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
const { state, fetchDetail, updateSc, submitSc, approveSc, denySc, closeSc } = useSc()
const { createPo, updatePo, finishPo, submitPo } = usePo()
const { state: vendorState, searchVendors } = useVendor()
const { exportRows } = useExport()

const scId = computed(() => route.params.id)
const detail = computed(() => state.detail || {})
const permissions = computed(() => detail.value.permissions || {})
const vendors = computed(() => vendorState.rows)
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
    ElMessage.success(t('sc.updated'))
    await fetchDetail(scId.value)
    editDialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
}

async function handleSubmit() {
  try {
    await ElMessageBox.confirm(t('sc.confirmSubmit'), t('common.confirm'), { type: 'warning' })
    await submitSc(scId.value, {})
    ElMessage.success(t('sc.submitted'))
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
    await ElMessageBox.confirm(t('sc.confirmApprove'), t('common.confirm'), { type: 'warning' })

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
    ElMessage.success(t('sc.approved'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleDeny() {
  try {
    await ElMessageBox.confirm(t('sc.confirmDeny'), t('common.confirm'), { type: 'warning' })
    await denySc(scId.value)
    ElMessage.success(t('sc.denied'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleClose() {
  try {
    await ElMessageBox.prompt(t('sc.confirmClosePrompt'), t('sc.closeSc'), {
      confirmButtonText: t('common.close'),
      type: 'warning',
      inputPattern: /^I CONFIRM CLOSE THIS SC$/,
      inputErrorMessage: t('sc.closeInputError'),
      inputPlaceholder: 'I CONFIRM CLOSE THIS SC'
    })
    await closeSc(scId.value)
    ElMessage.success(t('sc.closed'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function handleRevoke() {
  try {
    const status = detail.value.sc?.status
    const messages = {
      manager_confirm: { confirm: 'sc.confirmRevoke',   success: 'sc.revoked' },
      pending:         { confirm: 'sc.confirmRevokePending', success: 'sc.revoked' },
      approved:        { confirm: 'sc.confirmRollback', success: 'sc.rolledBack' },
      closed:          { confirm: 'sc.confirmRollback', success: 'sc.rolledBack' },
    }
    const msg = messages[status] || messages.pending
    await ElMessageBox.confirm(t(msg.confirm), t('common.confirm'), { type: 'warning' })
    await callApi('revoke_sc', { sc_id: scId.value })
    ElMessage.success(t(msg.success))
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
    { key: 'created_at', label: t('audit.created'), getValue: r => (r.created_at || '').slice(0, 19) },
    { key: 'action_type', label: t('audit.action') },
    { key: 'object_type', label: t('audit.objectType') },
    { key: 'object_id', label: t('audit.objectId') },
    { key: 'operator_id', label: t('audit.operator') },
    { key: 'machine_id', label: t('audit.machine') }
  ]
  const scNo = detail.value.sc?.sc_no || detail.value.sc?.sc_id || 'SC'
  await exportRows(detail.value.audit_logs || [], columns, `${scNo}_Audit`)
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
