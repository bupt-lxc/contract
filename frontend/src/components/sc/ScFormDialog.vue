<template>
  <el-dialog
    :model-value="visible"
    :title="mode === 'edit' ? 'Edit SC' : 'New SC'"
    width="640px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-row :gutter="16">
        <el-col :span="24">
          <el-form-item label="SC No" prop="sc_no">
            <el-input v-model="form.sc_no" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="Requester" prop="requester_id">
            <el-select v-model="form.requester_id" filterable>
              <el-option v-for="u in users" :key="u.user_id" :label="`${u.user_name} — ${u.machine_id}`" :value="u.user_id" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="Request Type" prop="request_type">
            <el-select v-model="form.request_type">
              <el-option v-for="t in requestTypes" :key="t" :label="t" :value="t" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="Cost Center" prop="cost_center">
            <el-input v-model="form.cost_center" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="SC Amount" prop="sc_amount">
            <el-input-number v-model="form.sc_amount" :precision="2" :min="0" controls-position="right" style="width:100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="Service Period Start" prop="service_period_start">
            <el-date-picker v-model="form.service_period_start" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="Service Period End" prop="service_period_end">
            <el-date-picker v-model="form.service_period_end" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="Description">
        <el-input v-model="form.description" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)" :disabled="submitting">Cancel</el-button>
      <el-button v-if="mode === 'create'" @click="saveDraft" :disabled="submitting">Save Draft</el-button>
      <el-button type="primary" @click="saveSubmit" :loading="submitting">
        {{ mode === 'edit' ? 'Save' : 'Submit' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  visible: { type: Boolean, default: false },
  mode: { type: String, default: 'create' },
  record: { type: Object, default: null },
  users: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:visible', 'save-draft', 'save-submit'])

const requestTypes = ['material', 'service', 'fixed_asset', 'FC']
const formRef = ref()
const submitting = ref(false)

const emptyForm = () => ({
  sc_no: '',
  requester_id: '',
  request_type: '',
  cost_center: '',
  sc_amount: null,
  service_period_start: null,
  service_period_end: null,
  description: ''
})

const form = reactive(emptyForm())

const draftRules = {
  requester_id: [{ required: true, message: 'Requester is required', trigger: 'change' }],
  sc_no: [{ required: true, message: 'SC No is required', trigger: 'change' }]
}
const submitRules = {
  requester_id: [{ required: true, message: 'Requester is required', trigger: 'change' }],
  sc_no: [{ required: true, message: 'SC No is required', trigger: 'change' }],
  request_type: [{ required: true, message: 'Request Type is required', trigger: 'change' }],
  cost_center: [{ required: true, message: 'Cost Center is required', trigger: 'change' }],
  sc_amount: [{ required: true, message: 'SC Amount is required', trigger: 'change' }],
  service_period_start: [{ required: true, message: 'Service Period Start is required', trigger: 'change' }],
  service_period_end: [{ required: true, message: 'Service Period End is required', trigger: 'change' }]
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
    if (props.mode === 'edit' && props.record) {
      Object.assign(form, props.record)
    } else {
      Object.assign(form, emptyForm())
    }
    _setRules(draftRules)
  }
})

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
    emit('save-draft', { ...form })
    emit('update:visible', false)
    ElMessage.success('Draft saved')
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
    emit('save-submit', { ...form })
    emit('update:visible', false)
    ElMessage.success('Saved')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}
</script>
