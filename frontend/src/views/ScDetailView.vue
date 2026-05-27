<template>
  <div>
    <div class="detail-page-header">
      <div>
        <h2>{{ detail.sc?.sc_no || detail.sc?.sc_id || 'SC Detail' }}</h2>
        <p>
          <StatusBadge v-if="detail.sc" :status="detail.sc.status" />
          <span v-if="detail.sc" style="color:#94a3b8;margin-left:8px">{{ detail.sc.request_type }}</span>
        </p>
      </div>
      <div class="header-actions">
        <el-button v-if="permissions.can_edit_sc" @click="openEditDialog">Edit</el-button>
        <el-button v-if="permissions.can_submit_sc" type="primary" @click="handleSubmit">Submit</el-button>
        <el-button v-if="permissions.can_approve_sc" type="success" @click="handleApprove">Approve</el-button>
        <el-button v-if="permissions.can_deny_sc" type="warning" @click="handleDeny">Deny</el-button>
        <el-button v-if="permissions.can_close_sc" type="danger" @click="handleClose">Close</el-button>
      </div>
    </div>

    <div v-if="state.detailLoading" class="section-card">
      <el-skeleton :rows="5" animated />
    </div>

    <el-alert v-if="state.detailError" :title="state.detailError" type="error" show-icon style="margin-bottom:16px" />

    <template v-if="detail.sc">
      <div class="section-card">
        <div class="section-header">
          <h3>SC Information</h3>
        </div>
        <ScDetailCard :sc="detail.sc" />
      </div>

      <div class="section-card">
        <div class="section-header">
          <h3>PO Records</h3>
          <el-button v-if="permissions.can_manage_po" type="primary" size="small" @click="poDialogVisible = true; poDialogMode = 'create'; poDialogRecord = null">
            <el-icon><Plus /></el-icon> Add PO
          </el-button>
        </div>
        <PoTable
          :rows="detail.pos || []"
          @row-click="row => $router.push(`/sc/${scId}/po/${row.po_id}`)"
          @edit="row => { poDialogRecord = { ...row, sc_id: scId }; poDialogMode = 'edit'; poDialogVisible = true }"
          @approve="row => handlePoApprove(row)"
          @finish="row => handlePoFinish(row)"
        />
      </div>

      <div class="section-card">
        <h3>Audit</h3>
        <el-table :data="detail.audit_logs || []" stripe border size="small">
          <el-table-column prop="created_at" label="Created" width="160">
            <template #default="{ row }">{{ row.created_at?.slice(0,19) }}</template>
          </el-table-column>
          <el-table-column prop="action_type" label="Action" width="140" />
          <el-table-column prop="object_type" label="Object" width="100" />
          <el-table-column prop="object_id" label="Object ID" width="120" />
          <el-table-column prop="operator_id" label="Operator" width="120" />
          <el-table-column prop="machine_id" label="Machine" min-width="120" />
          <template #empty><el-empty description="No audit records." /></template>
        </el-table>
      </div>
    </template>

    <ScFormDialog
      v-model:visible="editDialogVisible"
      mode="edit"
      :record="detail.sc"
      :users="activeUsers"
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
import { useRoute } from 'vue-router'
import { Plus } from '@element-plus/icons-vue'
import { useSc } from '@/composables/useSc.js'
import { usePo } from '@/composables/usePo.js'
import { useVendor } from '@/composables/useVendor.js'
import { callApi } from '@/api/bridge.js'
import StatusBadge from '@/components/common/StatusBadge.vue'
import ScDetailCard from '@/components/sc/ScDetailCard.vue'
import ScFormDialog from '@/components/sc/ScFormDialog.vue'
import PoTable from '@/components/po/PoTable.vue'
import PoFormDialog from '@/components/po/PoFormDialog.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const { state, fetchDetail, updateSc, submitSc, approveSc, denySc, closeSc } = useSc()
const { createPo, updatePo, approvePo, finishPo } = usePo()
const { state: vendorState, searchVendors } = useVendor()

const scId = computed(() => route.params.id)
const detail = computed(() => state.detail || {})
const permissions = computed(() => detail.value.permissions || {})
const vendors = computed(() => vendorState.rows)
const activeUsers = ref([])

const editDialogVisible = ref(false)
const poDialogVisible = ref(false)
const poDialogMode = ref('create')
const poDialogRecord = ref(null)

function openEditDialog() { editDialogVisible.value = true }

async function handleEditSave(data) {
  try {
    await updateSc(data)
    ElMessage.success('SC updated')
    await fetchDetail(scId.value)
  } catch (e) { ElMessage.error(e.message); throw e }
}

async function handleSubmit() {
  try {
    await ElMessageBox.confirm('Submit this SC?', 'Confirm', { type: 'warning' })
    await submitSc({ sc_id: scId.value })
    ElMessage.success('SC submitted')
    await fetchDetail(scId.value)
  } catch { /* cancelled */ }
}

async function handleApprove() {
  try {
    await ElMessageBox.confirm('Approve this SC?', 'Confirm', { type: 'warning' })
    await approveSc(scId.value)
    ElMessage.success('SC approved')
    await fetchDetail(scId.value)
  } catch { /* cancelled */ }
}

async function handleDeny() {
  try {
    await ElMessageBox.confirm('Deny this SC?', 'Confirm', { type: 'warning' })
    await denySc(scId.value)
    ElMessage.success('SC denied')
    await fetchDetail(scId.value)
  } catch { /* cancelled */ }
}

async function handleClose() {
  try {
    await ElMessageBox.prompt('Type "I CONFIRM CLOSE THIS SC" to proceed.', 'Close SC', {
      confirmButtonText: 'Close',
      type: 'warning',
      inputPattern: /^I CONFIRM CLOSE THIS SC$/,
      inputErrorMessage: 'Type the confirmation text exactly.'
    })
    await closeSc(scId.value)
    ElMessage.success('SC closed')
    await fetchDetail(scId.value)
  } catch { /* cancelled */ }
}

async function handlePoApprove(row) {
  try {
    await ElMessageBox.confirm('Approve this PO?', 'Confirm', { type: 'warning' })
    await approvePo(row.po_id)
    ElMessage.success('PO approved')
    await fetchDetail(scId.value)
  } catch { /* cancelled */ }
}

async function handlePoFinish(row) {
  try {
    await ElMessageBox.confirm('Finish this PO?', 'Confirm', { type: 'warning' })
    await finishPo(row.po_id)
    ElMessage.success('PO finished')
    await fetchDetail(scId.value)
  } catch { /* cancelled */ }
}

async function handlePoSave(data) {
  try {
    if (poDialogMode.value === 'create') {
      await createPo({ ...data, sc_id: scId.value })
    } else {
      await updatePo(data)
    }
    ElMessage.success('Saved')
    await fetchDetail(scId.value)
    poDialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
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
