<template>
  <div class="section-card">
    <h3 style="margin-bottom:12px">{{ $t('notification.notificationDefaults') }}</h3>

    <div v-if="loading">{{ $t('common.loading') }}</div>
    <template v-else>
      <!-- Admin Recipients -->
      <div style="margin-bottom:16px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">{{ $t('notification.adminRecipients') }}</label>
        <el-select
          v-model="local.admin_recipients"
          multiple
          filterable
          :placeholder="$t('notification.selectAdminsPlaceholder')"
          style="width:100%"
          @change="emitSave"
        >
          <el-option
            v-for="u in adminUsers"
            :key="u.user_id"
            :label="`${u.user_name} -- ${u.machine_id}`"
            :value="u.user_id"
          />
        </el-select>
      </div>

      <!-- Transition Rules — plain layout to avoid el-table rendering issues in PyWebView -->
      <div v-for="et in ['sc','po','gr']" :key="et" style="margin-bottom:16px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">{{ $t(`notification.${et}TransitionRules`) }}</label>
        <div class="transition-rules-card">
          <div v-for="tKey in transitionKeys(et)" :key="`${et}-${tKey}`" class="transition-rule-row">
            <span class="transition-rule-label">{{ tKey }}</span>
            <div class="transition-rule-selects">
              <el-select
                :model-value="local.transitions[et][tKey].to"
                @update:model-value="(v) => { local.transitions[et][tKey].to = v; emitSave() }"
                multiple
                :placeholder="$t('notification.to')"
                style="flex:1;min-width:180px"
              >
                <el-option :label="$t('notification.adminRecipients')" value="notify.admin_recipients" />
                <el-option :label="$t('notification.requester')" value="requester" />
                <el-option :label="$t('notification.actor')" value="actor" />
              </el-select>
              <el-select
                :model-value="local.transitions[et][tKey].cc"
                @update:model-value="(v) => { local.transitions[et][tKey].cc = v; emitSave() }"
                multiple
                :placeholder="$t('notification.cc')"
                style="flex:1;min-width:180px"
              >
                <el-option :label="$t('notification.adminRecipients')" value="notify.admin_recipients" />
                <el-option :label="$t('notification.requester')" value="requester" />
                <el-option :label="$t('notification.actor')" value="actor" />
              </el-select>
            </div>
          </div>
        </div>
      </div>

      <!-- Default CC -->
      <div style="margin-bottom:16px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">{{ $t('notification.defaultCcList') }}</label>
        <el-select v-model="local.default_cc" multiple filterable
          :placeholder="$t('notification.selectUsersPlaceholder')" style="width:100%" @change="emitSave">
          <el-option v-for="u in allUsers" :key="u.user_id"
            :label="`${u.user_name} -- ${u.machine_id}`" :value="u.user_id" />
        </el-select>
      </div>

      <!-- Thresholds -->
      <div style="margin-bottom:16px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">{{ $t('notification.defaultDateThresholds') }}</label>
        <el-checkbox-group v-model="local.date_thresholds" @change="emitSave">
          <el-checkbox :label="6">{{ $t('notification.sixMonths') }}</el-checkbox>
          <el-checkbox :label="3">{{ $t('notification.threeMonths') }}</el-checkbox>
          <el-checkbox :label="1">{{ $t('notification.oneMonth') }}</el-checkbox>
          <el-checkbox :label="0.5">{{ $t('notification.twoWeeks') }}</el-checkbox>
        </el-checkbox-group>
      </div>
      <div>
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">{{ $t('notification.defaultAmountThresholds') }}</label>
        <el-checkbox-group v-model="local.amount_thresholds" @change="emitSave">
          <el-checkbox :label="50">{{ $t('notification.fiftyPercent') }}</el-checkbox>
          <el-checkbox :label="30">{{ $t('notification.thirtyPercent') }}</el-checkbox>
          <el-checkbox :label="10">{{ $t('notification.tenPercent') }}</el-checkbox>
        </el-checkbox-group>
      </div>
    </template>
  </div>
</template>

<style scoped>
.transition-rules-card {
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 4px 0;
}
.transition-rule-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 12px;
  border-bottom: 1px solid #ebeef5;
}
.transition-rule-row:last-child {
  border-bottom: none;
}
.transition-rule-label {
  width: 80px;
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 500;
  color: #606266;
}
.transition-rule-selects {
  display: flex;
  gap: 8px;
  flex: 1;
}
</style>

<script setup>
import { reactive, watch, computed } from 'vue'

const props = defineProps({
  defaults: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  users: { type: Array, default: () => [] }
})

const emit = defineEmits(['save'])

const adminUsers = computed(() => props.users.filter(u => u.role === 'admin'))
const allUsers = computed(() => props.users)

const local = reactive({
  admin_recipients: [],
  transitions: {
    sc: { submit: { to: [], cc: [] }, confirm: { to: [], cc: [] }, approve: { to: [], cc: [] }, deny: { to: [], cc: [] }, close: { to: [], cc: [] }, revoke: { to: [], cc: [] } },
    po: { create: { to: [], cc: [] }, submit: { to: [], cc: [] }, finish: { to: [], cc: [] }, revoke: { to: [], cc: [] } },
    gr: { create: { to: [], cc: [] }, submit: { to: [], cc: [] }, confirm: { to: [], cc: [] }, approve: { to: [], cc: [] }, cancel: { to: [], cc: [] }, revoke: { to: [], cc: [] } }
  },
  default_cc: [],
  date_thresholds: [],
  amount_thresholds: []
})

watch(() => props.defaults, (val) => {
  if (val) {
    // Update arrays in-place to preserve reactivity references
    const ar = val['notify.admin_recipients']
    local.admin_recipients.splice(0, local.admin_recipients.length, ...(Array.isArray(ar) ? ar : []))

    // Deep-assign transitions to keep existing reactive objects alive.
    // Replacing the whole object can cause el-select inside el-table to lose
    // its v-model binding during re-render cycles.
    for (const et of ['sc', 'po', 'gr']) {
      const src = val[`notify.transitions.${et}`]
      if (src) {
        for (const tKey of Object.keys(src)) {
          if (local.transitions[et][tKey]) {
            local.transitions[et][tKey].to = src[tKey].to || []
            local.transitions[et][tKey].cc = src[tKey].cc || []
          } else {
            local.transitions[et][tKey] = { to: src[tKey].to || [], cc: src[tKey].cc || [] }
          }
        }
      }
    }

    const dcc = val['notify.default_cc']
    local.default_cc.splice(0, local.default_cc.length, ...(Array.isArray(dcc) ? dcc : []))

    const dt = val['notify.default_date_thresholds']
    local.date_thresholds.splice(0, local.date_thresholds.length, ...(Array.isArray(dt) ? dt : []))

    const at = val['notify.default_amount_thresholds']
    local.amount_thresholds.splice(0, local.amount_thresholds.length, ...(Array.isArray(at) ? at : []))

  } else {
    // val is falsy, keeping hardcoded defaults
  }
}, { immediate: true })

function transitionKeys(entityType) {
  return Object.keys(local.transitions[entityType])
}

let saveTimer = null
function emitSave() {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    emit('save', {
      admin_recipients: local.admin_recipients,
      transitions: local.transitions,
      default_cc: local.default_cc,
      date_thresholds: local.date_thresholds,
      amount_thresholds: local.amount_thresholds
    })
  }, 300)
}
</script>
