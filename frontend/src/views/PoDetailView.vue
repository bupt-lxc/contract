<template>
  <div>
    <div class="detail-page-header">
      <div>
        <h2>{{ po.po_no || po.po_id || 'PO Detail' }}</h2>
        <p><StatusBadge v-if="po.status" :status="po.status" /></p>
      </div>
      <div class="header-actions">
        <el-button v-if="scDetail?.permissions?.can_manage_po" @click="openEditDialog">Edit</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_po && po.status === 'po_pending'" type="success" @click="handleApprove">Approve</el-button>
        <el-button v-if="scDetail?.permissions?.can_manage_po && po.status === 'po_approved'" type="info" @click="handleFinish">Finish</el-button>
      </div>
    </div>

    <div v-if="!po.po_id" class="section-card">
      <el-empty description="PO not found." />
    </div>

    <template v-if="po.po_id">
      <div class="section-card">
        <h3 style="margin-bottom:12px">PO Information</h3>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="PO ID">{{ po.po_id }}</el-descriptions-item>
          <el-descriptions-item label="PO No">{{ po.po_no || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Vendor">{{ po.vendor_name || po.vendor_id }}</el-descriptions-item>
          <el-descriptions-item label="PO Amount"><AmountDisplay :value="po.po_amount" /></el-descriptions-item>
          <el-descriptions-item label="Contract From">{{ po.contract_from?.slice(0,10) || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Contract To">{{ po.contract_to?.slice(0,10) || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Contract No">{{ po.contract_no || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Payment Freq">{{ po.payment_frequency || '-' }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <div class="section-card">
        <div class="section-header">
          <h3>GR Records</h3>
          <el-button v-if="scDetail?.permissions?.can_manage_gr" type="primary" size="small" @click="grDialogVisible = true; grDialogMode = 'create'; grDialogRecord = null">
            <el-icon><Plus /></el-icon> Add GR
          </el-button>
        </div>
        <GrTable
          :rows="grs"
          @edit="row => { grDialogRecord = { ...row, po_id: poId }; grDialogMode = 'edit'; grDialogVisible = true }"
          @approve="row => handleGrApprove(row)"
          @cancel="row => handleGrCancel(row)"
        />
      </div>
    </template>

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
import { useRoute } from 'vue-router'
import { Plus } from '@element-plus/icons-vue'
import { useSc } from '@/composables/useSc.js'
import { usePo } from '@/composables/usePo.js'
import { useGr } from '@/composables/useGr.js'
import { useVendor } from '@/composables/useVendor.js'
import StatusBadge from '@/components/common/StatusBadge.vue'
import AmountDisplay from '@/components/common/AmountDisplay.vue'
import PoFormDialog from '@/components/po/PoFormDialog.vue'
import GrTable from '@/components/po/GrTable.vue'
import GrFormDialog from '@/components/po/GrFormDialog.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const { state: scState, fetchDetail } = useSc()
const { updatePo, approvePo, finishPo } = usePo()
const { createGr, updateGr, approveGr, cancelGr } = useGr()
const { state: vendorState, searchVendors } = useVendor()

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

function openEditDialog() { editDialogVisible.value = true }

async function handleEditSave(data) {
  try {
    await updatePo(data)
    ElMessage.success('PO updated')
    await fetchDetail(scId.value)
  } catch (e) { ElMessage.error(e.message); throw e }
}

async function handleApprove() {
  try {
    await ElMessageBox.confirm('Approve this PO?', 'Confirm', { type: 'warning' })
    await approvePo(poId.value)
    ElMessage.success('PO approved')
    await fetchDetail(scId.value)
  } catch {}
}

async function handleFinish() {
  try {
    await ElMessageBox.confirm('Finish this PO?', 'Confirm', { type: 'warning' })
    await finishPo(poId.value)
    ElMessage.success('PO finished')
    await fetchDetail(scId.value)
  } catch {}
}

async function handleGrApprove(row) {
  try {
    await ElMessageBox.confirm('Approve this GR?', 'Confirm', { type: 'warning' })
    await approveGr(row.gr_id)
    ElMessage.success('GR approved')
    await fetchDetail(scId.value)
  } catch {}
}

async function handleGrCancel(row) {
  try {
    await ElMessageBox.confirm('Cancel this GR?', 'Confirm', { type: 'warning' })
    await cancelGr(row.gr_id)
    ElMessage.success('GR cancelled')
    await fetchDetail(scId.value)
  } catch {}
}

async function handleGrSave(data) {
  try {
    if (grDialogMode.value === 'create') {
      await createGr({ ...data, po_id: poId.value })
    } else {
      await updateGr(data)
    }
    ElMessage.success('Saved')
    await fetchDetail(scId.value)
    grDialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
}

onMounted(async () => {
  await Promise.all([fetchDetail(scId.value), searchVendors()])
})
</script>
