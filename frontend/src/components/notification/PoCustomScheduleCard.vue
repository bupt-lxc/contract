<template>
  <div class="section-card">
    <div class="section-header">
      <h3>{{ $t('notification.customSchedules') }}</h3>
      <el-button size="small" type="primary" @click="openAddDialog">
        + {{ $t('notification.addSchedule') }}
      </el-button>
    </div>

    <el-empty
      v-if="!schedules.length"
      :description="$t('notification.noCustomSchedules')"
      :image-size="60"
    />

    <div v-else class="schedule-list">
      <el-tag
        v-for="s in schedules"
        :key="s.id"
        closable
        size="default"
        class="schedule-tag"
        @close="removeSchedule(s)"
      >
        {{ describeSchedule(s) }}
      </el-tag>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="$t('notification.addSchedule')"
      width="480px"
      @closed="resetDialog"
    >
      <el-form label-position="top">
        <el-form-item :label="$t('notification.scheduleType')">
          <el-select v-model="dialog.type" style="width:100%">
            <el-option :label="$t('notification.monthlyDay')" value="monthly_day" />
            <el-option :label="$t('notification.monthlyWeekday')" value="monthly_weekday" />
            <el-option :label="$t('notification.weeklyDay')" value="weekly_day" />
          </el-select>
        </el-form-item>

        <!-- monthly_day: pick day 1-31 -->
        <el-form-item v-if="dialog.type === 'monthly_day'" :label="$t('notification.dayOfMonth')">
          <el-input-number v-model="dialog.dayOfMonth" :min="1" :max="31" style="width:100%" />
        </el-form-item>

        <!-- monthly_weekday: pick occurrence + weekday -->
        <template v-if="dialog.type === 'monthly_weekday'">
          <el-form-item :label="$t('notification.occurrence')">
            <el-select v-model="dialog.occurrence" style="width:100%">
              <el-option :label="$t('notification.occurrenceFirst')" value="first" />
              <el-option :label="$t('notification.occurrenceSecond')" value="second" />
              <el-option :label="$t('notification.occurrenceThird')" value="third" />
              <el-option :label="$t('notification.occurrenceFourth')" value="fourth" />
              <el-option :label="$t('notification.occurrenceLast')" value="last" />
            </el-select>
          </el-form-item>
          <el-form-item :label="$t('notification.weekday')">
            <el-select v-model="dialog.weekday" style="width:100%">
              <el-option v-for="wd in weekdays" :key="wd.value" :label="wd.label" :value="wd.value" />
            </el-select>
          </el-form-item>
        </template>

        <!-- weekly_day: pick weekday -->
        <el-form-item v-if="dialog.type === 'weekly_day'" :label="$t('notification.weekday')">
          <el-select v-model="dialog.weekday" style="width:100%">
            <el-option v-for="wd in weekdays" :key="wd.value" :label="wd.label" :value="wd.value" />
          </el-select>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="confirmAdd">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({
  poId: { type: String, required: true },
  schedules: { type: Array, default: () => [] }
})

const emit = defineEmits(['save'])

const dialogVisible = ref(false)

// 0=Monday...6=Sunday (Python date.weekday() convention)
const weekdays = [
  { value: 0, labelKey: 'notification.weekdayMon' },
  { value: 1, labelKey: 'notification.weekdayTue' },
  { value: 2, labelKey: 'notification.weekdayWed' },
  { value: 3, labelKey: 'notification.weekdayThu' },
  { value: 4, labelKey: 'notification.weekdayFri' },
  { value: 5, labelKey: 'notification.weekdaySat' },
  { value: 6, labelKey: 'notification.weekdaySun' },
].map(w => ({ ...w, label: t(w.labelKey) }))

const weekdayLabels = Object.fromEntries(weekdays.map(w => [w.value, w.label]))

const occurrenceLabels = {
  first: () => t('notification.occurrenceFirst'),
  second: () => t('notification.occurrenceSecond'),
  third: () => t('notification.occurrenceThird'),
  fourth: () => t('notification.occurrenceFourth'),
  last: () => t('notification.occurrenceLast'),
}

const dialog = reactive({
  type: 'monthly_day',
  dayOfMonth: 1,
  weekday: 0,
  occurrence: 'first'
})

function openAddDialog() {
  resetDialog()
  dialogVisible.value = true
}

function resetDialog() {
  dialog.type = 'monthly_day'
  dialog.dayOfMonth = 1
  dialog.weekday = 0
  dialog.occurrence = 'first'
}

function confirmAdd() {
  const newSchedule = { schedule_type: dialog.type }
  if (dialog.type === 'monthly_day') {
    newSchedule.day_of_month = dialog.dayOfMonth
  } else if (dialog.type === 'monthly_weekday') {
    newSchedule.weekday = dialog.weekday
    newSchedule.occurrence = dialog.occurrence
  } else if (dialog.type === 'weekly_day') {
    newSchedule.weekday = dialog.weekday
  }
  const updated = [...props.schedules.map(s => ({ ...s })), newSchedule]
  emit('save', updated)
  dialogVisible.value = false
}

function removeSchedule(schedule) {
  const updated = props.schedules.filter(s => s !== schedule).map(s => ({ ...s }))
  emit('save', updated)
}

function describeSchedule(s) {
  if (s.schedule_type === 'monthly_day') {
    return t('notification.scheduleMonthlyDayLabel', { day: s.day_of_month })
  }
  if (s.schedule_type === 'monthly_weekday') {
    const occ = occurrenceLabels[s.occurrence]?.() || s.occurrence
    const wd = weekdayLabels[s.weekday] || s.weekday
    return t('notification.scheduleMonthlyWeekdayLabel', { occ, wd })
  }
  if (s.schedule_type === 'weekly_day') {
    const wd = weekdayLabels[s.weekday] || s.weekday
    return t('notification.scheduleWeeklyDayLabel', { wd })
  }
  return s.schedule_type
}
</script>

<style scoped>
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.section-header h3 {
  margin: 0;
}
.schedule-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.schedule-tag {
  font-size: 13px;
}
</style>
