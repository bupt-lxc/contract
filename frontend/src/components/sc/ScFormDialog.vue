<template>
  <el-dialog
    :model-value="visible"
    :title="mode === 'edit' ? $t('sc.editSc') : $t('sc.newSc')"
    width="640px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-row :gutter="16">
        <el-col :span="24">
          <el-form-item :label="$t('sc.scNo')" prop="sc_no">
            <el-input v-model="form.sc_no" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('sc.requester')" prop="requester_id">
            <el-select v-model="form.requester_id" filterable>
              <el-option v-for="u in users" :key="u.user_id" :label="`${u.user_name} — ${u.machine_id}`" :value="u.user_id" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('sc.requestType')" prop="request_type">
            <el-select v-model="form.request_type">
              <el-option v-for="t in requestTypes" :key="t" :label="t" :value="t" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('sc.costCenter')" prop="cost_center">
            <el-input v-model="form.cost_center" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('sc.scAmount')" prop="sc_amount">
            <el-input-number v-model="form.sc_amount" :precision="2" :min="0" controls-position="right" style="width:100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('sc.servicePeriodStart')" prop="service_period_start">
            <el-date-picker v-model="form.service_period_start" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('sc.servicePeriodEnd')" prop="service_period_end">
            <el-date-picker v-model="form.service_period_end" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="$t('sc.description')">
        <el-input v-model="form.description" type="textarea" :rows="3" />
      </el-form-item>
      <el-form-item :label="$t('sc.vendors')">
        <el-select
          v-model="form.vendor_ids"
          multiple
          filterable
          placeholder="Select vendors"
          style="width:100%"
        >
          <el-option
            v-for="v in vendors"
            :key="v.vendor_id"
            :label="`${v.vendor_name} — ${v.vendor_id}`"
            :value="v.vendor_id"
          />
        </el-select>
      </el-form-item>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('sc.asset')">
            <el-select v-model="form.asset">
              <el-option label="Y" value="Y" />
              <el-option label="N" value="N" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('sc.assetNums')">
            <el-input v-model="form.asset_nums" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item v-if="form.request_type === 'FC'" :label="$t('sc.internalSystemNumber')">
        <el-input v-model="form.internal_system_number" />
      </el-form-item>
      <el-form-item :label="$t('attachment.attachments')">
        <div>
          <el-button size="small" @click="handlePickFiles">
            <el-icon><Paperclip /></el-icon> {{ $t('attachment.addAttachment') }}
          </el-button>
          <div v-if="pickedFiles.length" style="margin-top:8px">
            <el-tag
              v-for="(f, i) in pickedFiles"
              :key="i"
              closable
              @close="pickedFiles.splice(i, 1)"
              size="small"
              style="margin-right:4px;margin-bottom:4px"
            >
              {{ f.name }}
            </el-tag>
          </div>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)" :disabled="submitting">{{ $t('common.cancel') }}</el-button>
      <el-button v-if="mode === 'create'" @click="saveDraft" :disabled="submitting">{{ $t('common.saveDraft') }}</el-button>
      <el-button type="primary" @click="saveSubmit" :loading="submitting">
        {{ mode === 'edit' ? $t('common.save') : $t('common.submit') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Paperclip } from '@element-plus/icons-vue'
import { callApi } from '@/api/bridge.js'
import { ElMessage } from 'element-plus'

const { t } = useI18n()

const props = defineProps({
  visible: { type: Boolean, default: false },
  mode: { type: String, default: 'create' },
  record: { type: Object, default: null },
  users: { type: Array, default: () => [] },
  vendors: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:visible', 'save-draft', 'save-submit'])

const requestTypes = ['material', 'service', 'fixed_asset', 'FC']
const formRef = ref()
const submitting = ref(false)
const pickedFiles = ref([])

const emptyForm = () => ({
  sc_no: '',
  requester_id: '',
  request_type: '',
  cost_center: '60473000',
  sc_amount: null,
  service_period_start: null,
  service_period_end: null,
  description: '',
  vendor_ids: [],
  asset: 'N',
  asset_nums: '',
  internal_system_number: ''
})

const form = reactive(emptyForm())

const draftRules = {
  requester_id: [{ required: true, message: t('sc.requesterRequired'), trigger: 'change' }]
}
const submitRules = {
  requester_id: [{ required: true, message: t('sc.requesterRequired'), trigger: 'change' }],
  request_type: [{ required: true, message: t('sc.requestTypeRequired'), trigger: 'change' }],
  cost_center: [{ required: true, message: t('sc.costCenterRequired'), trigger: 'change' }],
  sc_amount: [{ required: true, message: t('sc.scAmountRequired'), trigger: 'change' }],
  service_period_start: [{ required: true, message: t('sc.servicePeriodStartRequired'), trigger: 'change' }],
  service_period_end: [{ required: true, message: t('sc.servicePeriodEndRequired'), trigger: 'change' }]
}

const rules = reactive({})

function _setRules(source) {
  // Clear stale keys left by a previous rule-set, then assign the new ones
  Object.keys(rules).forEach(k => delete rules[k])
  Object.assign(rules, source)
}

watch(() => props.visible, (val) => {
  if (val) {
    formRef.value?.clearValidate()
    pickedFiles.value = []
    if (props.mode === 'edit' && props.record) {
      Object.assign(form, emptyForm(), props.record)
      // Populate vendor_ids from the vendors array in detail
      if (props.record.vendors?.length) {
        form.vendor_ids = props.record.vendors.map(v => v.vendor_id)
      }
    } else {
      Object.assign(form, emptyForm())
    }
    _setRules(draftRules)
  }
})

async function handlePickFiles() {
  try {
    const files = await callApi('pick_files')
    if (files?.length) pickedFiles.value.push(...files)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function _savePayload() {
  return { ...form, vendor_ids: form.vendor_ids || [], _attachments: pickedFiles.value.map(f => f.path) }
}

async function saveDraft() {
  if (!formRef.value) return
  _setRules(draftRules)
  formRef.value.clearValidate()
  try {
    await formRef.value.validate()
  } catch (err) {
    console.log('saveDraft validation failed:', err)
    return
  }
  submitting.value = true
  try {
    emit('save-draft', _savePayload())
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}

async function saveSubmit() {
  if (!formRef.value) return
  if (props.mode === 'create') {
    _setRules(submitRules)
    formRef.value.clearValidate()
    try {
      await formRef.value.validate()
    } catch (err) {
      console.log('saveSubmit validation failed:', err)
      return
    }
  }
  submitting.value = true
  try {
    emit('save-submit', _savePayload())
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}
</script>
