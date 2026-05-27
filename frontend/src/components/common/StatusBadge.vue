<template>
  <el-tag :type="tagType" size="small" :class="['status-badge', `status-row-${status}`]">
    {{ label }}
  </el-tag>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, required: true }
})

const STATUS_LABELS = {
  draft: 'Draft',
  pending: 'Pending',
  approved: 'Approved',
  denied: 'Denied',
  closed: 'Closed',
  po_pending: 'Pending',
  po_approved: 'Approved',
  finished: 'Finished',
  cancelled: 'Cancelled'
}

const STATUS_TYPES = {
  draft: '',
  pending: 'warning',
  approved: 'success',
  denied: 'danger',
  closed: 'info',
  po_pending: 'warning',
  po_approved: 'success',
  finished: 'info',
  cancelled: 'danger'
}

const tagType = computed(() => STATUS_TYPES[props.status] || 'info')
const label = computed(() => STATUS_LABELS[props.status] || props.status)
</script>
