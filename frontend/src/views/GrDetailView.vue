<template>
  <div>
    <div class="detail-page-header">
      <div>
        <h2>{{ gr.gr_id || $t('gr.grDetail') }}</h2>
        <p><StatusBadge v-if="gr.status" :status="gr.status" /></p>
      </div>
      <div class="header-actions">
        <el-button v-if="scDetail?.permissions?.can_manage_gr && gr.status === 'pending'" @click="openEditDialog">{{ $t('common.edit') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_gr && gr.status === 'pending'" type="success" @click="handleApprove">{{ $t('common.approve') }}</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_gr && gr.status === 'pending'" type="danger" @click="handleCancel">{{ $t('gr.cancel') }}</el-button>
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
          <el-descriptions-item :label="$t('gr.conValue')"><AmountDisplay :value="gr.con_value" /></el-descriptions-item>
          <el-descriptions-item :label="$t('gr.remark')" :span="2">{{ gr.remark || '-' }}</el-descriptions-item>
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
          <el-table-column prop="machine_id" :label="$t('audit.machine')" min-width="120" />
          <template #empty><el-empty :description="$t('audit.noRecordsInSc')" /></template>
        </el-table>
      </div>
    </template>

    <GrFormDialog
      v-model:visible="editDialogVisible"
      mode="edit"
      :record="gr"
      @save="handleEditSave"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { useSc } from '@/composables/useSc.js'
import { useGr } from '@/composables/useGr.js'
import { callApi } from '@/api/bridge.js'
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'
import AttachmentList from '@/components/common/AttachmentList.vue'
import GrFormDialog from '@/components/po/GrFormDialog.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
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

function openEditDialog() { editDialogVisible.value = true }

async function handleEditSave(data) {
  try {
    await updateGr(data.gr_id || grId.value, data)
    ElMessage.success(t('common.saved'))
    await fetchDetail(scId.value)
    editDialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
}

async function handleApprove() {
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
    await approveGr(grId.value, parseFloat(value))
    ElMessage.success(t('gr.grApproved'))
    await fetchDetail(scId.value)
  } catch {}
}

async function handleCancel() {
  try {
    await ElMessageBox.confirm(t('gr.cancelConfirm'), t('common.confirm'), { type: 'warning' })
    await cancelGr(grId.value)
    ElMessage.success(t('gr.grCancelled'))
    await fetchDetail(scId.value)
  } catch {}
}

onMounted(async () => {
  await fetchDetail(scId.value)
})
</script>
