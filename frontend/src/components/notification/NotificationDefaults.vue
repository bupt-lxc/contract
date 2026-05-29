<template>
  <div class="section-card">
    <h3 style="margin-bottom:12px">Notification Defaults</h3>

    <div v-if="loading">Loading...</div>
    <template v-else>
      <!-- Admin Recipients -->
      <div style="margin-bottom:16px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">Admin Recipients</label>
        <el-select
          v-model="local.admin_recipients"
          multiple
          filterable
          :teleported="false"
          placeholder="Select admins who receive notifications"
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
      <div style="margin-bottom:16px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">SC Transition Rules</label>
        <el-table :data="transitionRows('sc')" border size="small">
          <el-table-column prop="transition" label="Transition" width="100" />
          <el-table-column label="To" width="200">
            <template #default="{ row }">
              <el-select v-model="local.transitions.sc[row.transition].to" multiple filterable
                :teleported="false" style="width:100%" @change="emitSave">
                <el-option label="Admin Recipients" value="notify.admin_recipients" />
                <el-option label="Requester" value="requester" />
                <el-option label="Actor" value="actor" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="CC" width="200">
            <template #default="{ row }">
              <el-select v-model="local.transitions.sc[row.transition].cc" multiple filterable
                :teleported="false" style="width:100%" @change="emitSave">
                <el-option label="Admin Recipients" value="notify.admin_recipients" />
                <el-option label="Requester" value="requester" />
                <el-option label="Actor" value="actor" />
              </el-select>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- Default CC -->
      <div style="margin-bottom:16px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">Default CC List</label>
        <el-select v-model="local.default_cc" multiple filterable
          :teleported="false" placeholder="Select users" style="width:100%" @change="emitSave">
          <el-option v-for="u in allUsers" :key="u.user_id"
            :label="`${u.user_name} -- ${u.machine_id}`" :value="u.user_id" />
        </el-select>
      </div>

      <!-- Thresholds -->
      <div style="margin-bottom:16px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">Default Date Thresholds</label>
        <el-checkbox-group v-model="local.date_thresholds" @change="emitSave">
          <el-checkbox :label="6">6 months</el-checkbox>
          <el-checkbox :label="3">3 months</el-checkbox>
          <el-checkbox :label="1">1 month</el-checkbox>
          <el-checkbox :label="0.5">2 weeks</el-checkbox>
        </el-checkbox-group>
      </div>
      <div>
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">Default Amount Thresholds</label>
        <el-checkbox-group v-model="local.amount_thresholds" @change="emitSave">
          <el-checkbox :label="50">50%</el-checkbox>
          <el-checkbox :label="30">30%</el-checkbox>
          <el-checkbox :label="10">10%</el-checkbox>
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
    sc: { submit: { to: [], cc: [] }, approve: { to: [], cc: [] }, deny: { to: [], cc: [] }, close: { to: [], cc: [] } },
    po: { create: { to: [], cc: [] }, approve: { to: [], cc: [] }, finish: { to: [], cc: [] } },
    gr: { create: { to: [], cc: [] }, approve: { to: [], cc: [] }, cancel: { to: [], cc: [] } }
  },
  default_cc: [],
  date_thresholds: [],
  amount_thresholds: []
})

watch(() => props.defaults, (val) => {
  if (val) {
    local.admin_recipients = val['notify.admin_recipients'] || []
    local.transitions.sc = val['notify.transitions.sc'] || local.transitions.sc
    local.transitions.po = val['notify.transitions.po'] || local.transitions.po
    local.transitions.gr = val['notify.transitions.gr'] || local.transitions.gr
    local.default_cc = val['notify.default_cc'] || []
    local.date_thresholds = val['notify.default_date_thresholds'] || []
    local.amount_thresholds = val['notify.default_amount_thresholds'] || []
  }
}, { immediate: true })

function transitionRows(entityType) {
  return Object.keys(local.transitions[entityType]).map(t => ({
    transition: t
  }))
}

function emitSave() {
  emit('save', {
    admin_recipients: local.admin_recipients,
    transitions: local.transitions,
    default_cc: local.default_cc,
    date_thresholds: local.date_thresholds,
    amount_thresholds: local.amount_thresholds
  })
}
</script>
