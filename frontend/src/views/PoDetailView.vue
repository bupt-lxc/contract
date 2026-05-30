<template>
  <div>
    <div class="detail-page-header">
      <div>
        <h2>{{ po.po_no || po.po_id || $t('po.poDetail') }}</h2>
        <p><StatusBadge v-if="po.status" :status="po.status" /></p>
      </div>
      <div class="header-actions">
        <el-button v-if="scDetail?.permissions?.can_manage_po" @click="openEditDialog">{{ $t('common.edit') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_po && po.status === 'po_pending'" type="success" @click="handleApprove">{{ $t('common.approve') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_po && po.status === 'po_approved'" type="info" @click="handleFinish">{{ $t('common.finish') }}</el-button>
      </div>
    </div>

    <div v-if="!po.po_id" class="section-card">
      <el-empty :description="$t('po.poNotFound')" />
    </div>

    <template v-if="po.po_id">
      <div class="section-card">
        <h3 style="margin-bottom:12px">{{ $t('po.poInformation') }}</h3>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="$t('po.poId')">{{ po.po_id }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.poNo')">{{ po.po_no || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('common.vendor')">{{ po.vendor_name || po.vendor_id }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.poAmount')"><AmountDisplay :value="po.po_amount" /></el-descriptions-item>
          <el-descriptions-item :label="$t('po.contractFrom')">{{ po.contract_from?.slice(0,10) || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.contractTo')">{{ po.contract_to?.slice(0,10) || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.contractNo')">{{ po.contract_no || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('po.paymentFreq')">{{ po.payment_frequency || '-' }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <div class="section-card">
        <div class="section-header">
          <h3>{{ $t('attachment.attachments') }}</h3>
        </div>
        <AttachmentList
          entity-type="po"
          :entity-id="po.po_id"
        />
      </div>

      <div class="section-card">
        <div class="section-header">
          <h3>{{ $t('gr.grRecords') }}</h3>
          <el-button v-if="scDetail?.permissions?.can_manage_gr" type="primary" size="small" @click="grDialogVisible = true; grDialogMode = 'create'; grDialogRecord = null">
            <el-icon><Plus /></el-icon> {{ $t('gr.addGr') }}
          </el-button>
          <el-button size="small" @click="handleExportGrs">
            <el-icon><Download /></el-icon> {{ $t('common.export') }}
          </el-button>
        </div>
        <GrTable
          :rows="grs"
          @row-click="row => $router.push(`/sc/${scId}/po/${poId}/gr/${row.gr_id}`)"
          @edit="row => { grDialogRecord = { ...row, po_id: poId }; grDialogMode = 'edit'; grDialogVisible = true }"
          @approve="row => handleGrApprove(row)"
          @cancel="row => handleGrCancel(row)"
          @attachments="row => { grAttachRecord = row; grAttachVisible = true }"
        />
      </div>
    </template>

    <AttachmentDialog
      v-model:visible="grAttachVisible"
      entity-type="gr"
      :entity-id="grAttachRecord?.gr_id || ''"
    />

    <PoFormDialog
      v-model:visible="editDialogVisible"
      mode="edit"
      :record="po"
      :vendors="vendors"
      @save="handleEditSave"
    />

    <GrFormDialog
      v-model:visible="grDialogVisible"
      :mode="grDialogMode"
      :record="grDialogRecord"
      @save="handleGrSave"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { Plus, Download } from '@element-plus/icons-vue'
import { useSc } from '@/composables/useSc.js'
import { useExport } from '@/composables/useExport.js'
import { usePo } from '@/composables/usePo.js'
import { useGr } from '@/composables/useGr.js'
import { useVendor } from '@/composables/useVendor.js'
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'
import PoFormDialog from '@/components/po/PoFormDialog.vue'
import GrTable from '@/components/po/GrTable.vue'
import AttachmentList from '@/components/common/AttachmentList.vue'
import AttachmentDialog from '@/components/common/AttachmentDialog.vue'
import GrFormDialog from '@/components/po/GrFormDialog.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const { t } = useI18n()
const { state: scState, fetchDetail } = useSc()
const { updatePo, approvePo, finishPo } = usePo()
const { createGr, updateGr, approveGr, cancelGr } = useGr()
const { state: vendorState, searchVendors } = useVendor()
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
const vendors = computed(() => vendorState.rows)

const editDialogVisible = ref(false)
const grDialogVisible = ref(false)
const grDialogMode = ref('create')
const grDialogRecord = ref(null)
const grAttachVisible = ref(false)
const grAttachRecord = ref(null)

function openEditDialog() { editDialogVisible.value = true }

async function handleEditSave(data) {
  try {
    const { _attachments, ...formData } = data
    const targetPoId = formData.po_id || poId.value
    await updatePo(targetPoId, formData)
    if (_attachments?.length) {
      await callApi('add_attachments', { entity_type: 'po', entity_id: targetPoId, file_paths: _attachments })
    }
    ElMessage.success(t('po.poUpdated'))
    await fetchDetail(scId.value)
  } catch (e) { ElMessage.error(e.message); throw e }
}

async function handleApprove() {
  try {
    await ElMessageBox.confirm(t('po.approveConfirm'), t('common.confirm'), { type: 'warning' })
    await approvePo(poId.value)
    ElMessage.success(t('po.poApproved'))
    await fetchDetail(scId.value)
  } catch {}
}

async function handleFinish() {
  try {
    await ElMessageBox.confirm(t('po.finishConfirm'), t('common.confirm'), { type: 'warning' })
    await finishPo(poId.value)
    ElMessage.success(t('po.poFinished'))
    await fetchDetail(scId.value)
  } catch {}
}

async function handleGrApprove(row) {
  try {
    const { value } = await ElMessageBox.prompt(
      t('gr.enterConValue'),
      t('gr.approveGr'),
      {
        confirmButtonText: t('common.approve'),
        type: 'warning',
        inputPattern: /^\d+(\.\d{1,2})?$/,
        inputErrorMessage: t('gr.invalidNumber')
      }
    )
    await approveGr(row.gr_id, parseFloat(value))
    ElMessage.success(t('gr.grApproved'))
    await fetchDetail(scId.value)
  } catch {}
}

async function handleGrCancel(row) {
  try {
    await ElMessageBox.confirm(t('gr.cancelConfirm'), t('common.confirm'), { type: 'warning' })
    await cancelGr(row.gr_id)
    ElMessage.success(t('gr.grCancelled'))
    await fetchDetail(scId.value)
  } catch {}
}

async function handleExportGrs() {
  const columns = [
    { key: 'status', label: t('common.status') },
    { key: 'gr_id', label: t('gr.grId') },
    { key: 'requester_id', label: t('gr.requester') },
    { key: 'estimated_amount', label: t('gr.estimated') },
    { key: 'con_value', label: t('gr.conValue') },
    { key: 'remark', label: t('common.remark') }
  ]
  const poNo = po.value?.po_no || po.value?.po_id || 'PO'
  await exportRows(grs.value, columns, `${poNo}_GRs`)
  ElMessage.success(t('common.exportedSuccessfully'))
}

async function handleGrSave(data) {
  try {
    const { _attachments, ...formData } = data
    let grId
    if (grDialogMode.value === 'create') {
      const created = await createGr({ ...formData, po_id: poId.value })
      grId = created.gr_id
    } else {
      grId = formData.gr_id
      await updateGr(grId, formData)
    }
    if (_attachments?.length) {
      await callApi('add_attachments', { entity_type: 'gr', entity_id: grId, file_paths: _attachments })
    }
    ElMessage.success(t('common.saved'))
    await fetchDetail(scId.value)
    grDialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
}

onMounted(async () => {
  await Promise.all([fetchDetail(scId.value), searchVendors()])
})
</script>
