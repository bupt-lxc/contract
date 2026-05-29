<template>
  <div class="section-card">
    <div class="section-header">
      <h3>Notification Settings</h3>
      <el-switch v-model="local.enabled" @change="emitSave" />
    </div>
    <template v-if="local.enabled">
      <div style="margin-top:12px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">CC List</label>
        <el-select
          v-model="local.cc_user_ids"
          multiple
          filterable
          placeholder="Select users to CC"
          style="width:100%"
          @change="emitSave"
        >
          <el-option
            v-for="u in users"
            :key="u.user_id"
            :label="`${u.user_name} -- ${u.machine_id}`"
            :value="u.user_id"
          />
        </el-select>
      </div>
      <div style="margin-top:12px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">Date Thresholds</label>
        <el-checkbox-group v-model="local.date_thresholds" @change="emitSave">
          <el-checkbox :label="6">6 months</el-checkbox>
          <el-checkbox :label="3">3 months</el-checkbox>
          <el-checkbox :label="1">1 month</el-checkbox>
          <el-checkbox :label="0.5">2 weeks</el-checkbox>
        </el-checkbox-group>
      </div>
      <div style="margin-top:12px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">Amount Thresholds</label>
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
import { reactive, watch } from 'vue'

const props = defineProps({
  scId: { type: String, required: true },
  config: { type: Object, default: null },
  users: { type: Array, default: () => [] }
})

const emit = defineEmits(['save'])

const local = reactive({
  enabled: true,
  cc_user_ids: [],
  date_thresholds: [],
  amount_thresholds: []
})

watch(() => props.config, (val) => {
  if (val) {
    local.enabled = val.enabled
    local.cc_user_ids = val.cc_user_ids || []
    local.date_thresholds = val.date_thresholds || []
    local.amount_thresholds = val.amount_thresholds || []
  }
}, { immediate: true })

function emitSave() {
  emit('save', { ...local })
}
</script>
