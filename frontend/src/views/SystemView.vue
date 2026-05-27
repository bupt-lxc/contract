<template>
  <div>
    <div class="section-card">
      <h3 style="margin-bottom:12px">Current User</h3>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="Machine ID">{{ user?.machine_id }}</el-descriptions-item>
        <el-descriptions-item label="Name">{{ user?.user_name }}</el-descriptions-item>
        <el-descriptions-item label="Role"><el-tag size="small" :type="user?.role === 'admin' ? 'danger' : ''">{{ user?.role }}</el-tag></el-descriptions-item>
        <el-descriptions-item label="Email">{{ user?.email || '-' }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <div v-if="isAdmin" class="section-card">
      <div class="section-header">
        <h3>User Management</h3>
        <el-button type="primary" size="small" @click="dialogVisible = true; dialogMode = 'create'; dialogRecord = null">
          <el-icon><Plus /></el-icon> Add User
        </el-button>
      </div>
      <el-table :data="state.users" v-loading="state.loading" stripe border>
        <el-table-column prop="machine_id" label="Machine ID" width="120" />
        <el-table-column prop="user_name" label="Name" width="160" />
        <el-table-column prop="email" label="Email" min-width="180" />
        <el-table-column prop="role" label="Role" width="100" />
        <el-table-column label="Status" width="100">
          <template #default="{ row }"><StatusBadge :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="Actions" width="160" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="dialogVisible = true; dialogMode = 'edit'; dialogRecord = row">Edit</el-button>
            <el-popconfirm v-if="row.status === 'active'" title="Disable this user?" @confirm="handleDisable(row)">
              <template #reference><el-button type="danger" link size="small">Disable</el-button></template>
            </el-popconfirm>
            <el-popconfirm v-else title="Enable this user?" @confirm="handleEnable(row)">
              <template #reference><el-button type="success" link size="small">Enable</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
        <template #empty><el-empty description="No users found." /></template>
      </el-table>
    </div>

    <UserFormDialog
      v-model:visible="dialogVisible"
      :mode="dialogMode"
      :record="dialogRecord"
      @save="handleSave"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { useUser } from '@/composables/useUser.js'
import StatusBadge from '@/components/common/StatusBadge.vue'
import UserFormDialog from '@/components/system/UserFormDialog.vue'
import { ElMessage } from 'element-plus'

const { state, fetchUsers, createUser, updateUser, disableUser, enableUser } = useUser()

const user = computed(() => window.__currentUser || {})
const isAdmin = computed(() => user.value?.role === 'admin')

const dialogVisible = ref(false)
const dialogMode = ref('create')
const dialogRecord = ref(null)

async function handleSave(data) {
  try {
    if (dialogMode.value === 'create') {
      await createUser(data)
    } else {
      await updateUser(data.machine_id, data)
    }
    dialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
}

async function handleDisable(row) {
  try {
    await disableUser(row.machine_id)
    ElMessage.success('User disabled')
  } catch (e) { ElMessage.error(e.message) }
}

async function handleEnable(row) {
  try {
    await enableUser(row.machine_id)
    ElMessage.success('User enabled')
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(() => {
  if (isAdmin.value) fetchUsers()
})
</script>
