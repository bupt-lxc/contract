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
          :teleported="false"
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

      <!-- Transition Rules -->
      <div v-for="et in ['sc','po','gr']" :key="et" style="margin-bottom:16px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">{{ $t(`notification.${et}TransitionRules`) }}</label>
        <el-table :data="transitionRows(et)" border size="small">
          <el-table-column prop="transition" :label="$t('notification.transition')" width="100" />
          <el-table-column :label="$t('notification.to')" width="200">
            <template #default="{ row }">
              <el-select v-model="local.transitions[et][row.transition].to" multiple filterable
                :teleported="false" style="width:100%" @change="emitSave">
                <el-option :label="$t('notification.adminRecipients')" value="notify.admin_recipients" />
                <el-option :label="$t('notification.requester')" value="requester" />
                <el-option :label="$t('notification.actor')" value="actor" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column :label="$t('notification.cc')" width="200">
            <template #default="{ row }">
              <el-select v-model="local.transitions[et][row.transition].cc" multiple filterable
                :teleported="false" style="width:100%" @change="emitSave">
                <el-option :label="$t('notification.adminRecipients')" value="notify.admin_recipients" />
                <el-option :label="$t('notification.requester')" value="requester" />
                <el-option :label="$t('notification.actor')" value="actor" />
              </el-select>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- Default CC -->
      <div style="margin-bottom:16px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">{{ $t('notification.defaultCcList') }}</label>
        <el-select v-model="local.default_cc" multiple filterable
          :teleported="false" :placeholder="$t('notification.selectUsersPlaceholder')" style="width:100%" @change="emitSave">
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
  console.log('[NotifDefaults] watch fired, val:', JSON.stringify(val))
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

    console.log('[NotifDefaults] local.transitions.sc after watch:', JSON.stringify(local.transitions.sc))
  } else {
    console.log('[NotifDefaults] watch: val is falsy, keeping hardcoded defaults')
  }
}, { immediate: true })

function transitionRows(entityType) {
  return Object.keys(local.transitions[entityType]).map(t => ({
    transition: t
  }))
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
