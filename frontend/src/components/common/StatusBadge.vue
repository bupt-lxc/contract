<template>
  <el-tag :type="tagType" size="small" :class="['status-badge', `status-row-${status}`]">
    {{ label }}
  </el-tag>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  status: { type: String, required: true }
})

const { t } = useI18n()

const STATUS_LABELS = {
  draft: 'Draft',
  manager_confirm: 'Manager Confirm',
  pending: 'Pending',
  approved: 'Approved',
  denied: 'Denied',
  closed: 'Closed',
  activing: 'Activing',
  finished: 'Finished',
  cancelled: 'Cancelled'
}

const STATUS_TYPES = {
  draft: 'info',
  manager_confirm: '',
  pending: 'warning',
  approved: 'success',
  denied: 'danger',
  closed: 'info',
  activing: 'warning',
  finished: 'info',
  cancelled: 'danger'
}

const tagType = computed(() => STATUS_TYPES[props.status] || 'info')
const label = computed(() => t('status.' + props.status, props.status))
</script>
