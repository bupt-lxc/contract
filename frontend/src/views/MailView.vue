<template>
  <div>
    <div class="section-card">
      <div class="section-header">
        <h3>{{ $t('email.emailNotifications') }}</h3>
        <el-button type="primary" size="small" @click="$router.push('/emails/logs')">
          <el-icon><List /></el-icon> {{ $t('email.viewLogs') }}
        </el-button>
      </div>
    </div>

    <NotificationDefaults
      v-if="isAdmin"
      :defaults="notifState.defaults"
      :loading="notifState.defaultsLoading"
      :users="userState.users"
      @save="handleNotifDefaultsSave"
    />
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { List } from '@element-plus/icons-vue'
import { useNotification } from '@/composables/useNotification.js'
import { useUser } from '@/composables/useUser.js'
import NotificationDefaults from '@/components/notification/NotificationDefaults.vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const { state: notifState, fetchDefaults, saveDefaults } = useNotification()
const { state: userState, fetchUsers } = useUser()

const isAdmin = computed(() => window.__currentUser?.role === 'admin')

async function handleNotifDefaultsSave(data) {
  try {
    await saveDefaults(data)
    ElMessage.success(t('notification.defaultsSaved'))
  } catch (e) {
    ElMessage.error(t('notification.defaultsSaveFailed'))
  }
}

onMounted(() => {
  fetchDefaults()
  if (isAdmin.value) { fetchUsers() }
})
</script>
