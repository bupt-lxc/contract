<template>
  <div class="section-card">
    <div class="section-header">
      <h3>{{ $t('notification.notificationSettings') }}</h3>
      <el-switch v-model="local.enabled" @change="emitSave" />
    </div>
    <template v-if="local.enabled">
      <div style="margin-top:12px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">{{ $t('notification.ccList') }}</label>
        <el-select
          v-model="local.cc_user_ids"
          multiple
          filterable
          :teleported="false"
          :placeholder="$t('notification.selectCcUsers')"
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
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">{{ $t('notification.dateThresholds') }}</label>
        <el-checkbox-group v-model="local.date_thresholds" @change="emitSave" class="month-grid">
          <el-checkbox v-for="m in 12" :key="m" :value="13 - m">{{ 13 - m }} {{ $t('notification.months') }}</el-checkbox>
        </el-checkbox-group>
      </div>
      <div style="margin-top:12px">
        <label style="font-size:13px;color:#64748b;display:block;margin-bottom:4px">{{ $t('notification.amountThresholds') }}</label>
        <el-checkbox-group v-model="local.amount_thresholds" @change="emitSave">
          <el-checkbox :value="50">{{ $t('notification.fiftyPercent') }}</el-checkbox>
          <el-checkbox :value="30">{{ $t('notification.thirtyPercent') }}</el-checkbox>
          <el-checkbox :value="10">{{ $t('notification.tenPercent') }}</el-checkbox>
        </el-checkbox-group>
      </div>
    </template>
  </div>
</template>

<script setup>
import { reactive, watch } from 'vue'

const props = defineProps({
  poId: { type: String, required: true },
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

let saveTimer = null
function emitSave() {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    emit('save', { ...local })
  }, 300)
}
</script>

<style scoped>
.month-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 4px 0;
}
</style>
