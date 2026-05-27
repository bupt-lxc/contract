<template>
  <el-dialog
    :model-value="visible"
    :title="mode === 'edit' ? 'Edit Vendor' : 'Add Vendor'"
    width="520px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="Vendor ID" prop="vendor_id">
            <el-input v-model="form.vendor_id" :disabled="mode === 'edit'" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="Vendor Name" prop="vendor_name">
            <el-input v-model="form.vendor_name" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="Service Scope" prop="service_scope">
        <el-select v-model="form.service_scope" filterable>
          <el-option v-for="s in serviceScopes" :key="s" :label="s" :value="s" />
        </el-select>
      </el-form-item>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="KSRM Code">
            <el-input v-model="form.ksrm_vendor_code" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="Contact Person">
            <el-input v-model="form.contact_person" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="Phone">
            <el-input v-model="form.phone" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="Email">
            <el-input v-model="form.email" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="Description">
        <el-input v-model="form.description" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="Inquiry History">
        <el-input v-model="form.inquiry_history" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)" :disabled="submitting">Cancel</el-button>
      <el-button type="primary" @click="handleSave" :loading="submitting">Save</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  visible: Boolean,
  mode: { type: String, default: 'create' },
  record: Object
})

const emit = defineEmits(['update:visible', 'save'])

const formRef = ref()
const submitting = ref(false)

const serviceScopes = [
  'Transportation', 'engineering Service', 'Equipment', 'Parts', 'Driver',
  'Test car rental', 'General Service', 'Dealers', 'Import&Export&cusoms clearance',
  'Insurance', 'Harness', 'Maintenance', 'Security', 'Testing support', 'Others'
]

const emptyForm = () => ({
  vendor_id: '', vendor_name: '', service_scope: '', ksrm_vendor_code: '',
  contact_person: '', phone: '', email: '', description: '', inquiry_history: ''
})

const form = reactive(emptyForm())

const rules = {
  vendor_id: [{ required: true, message: 'Vendor ID is required', trigger: 'blur' }],
  vendor_name: [{ required: true, message: 'Vendor Name is required', trigger: 'blur' }],
  service_scope: [{ required: true, message: 'Service Scope is required', trigger: 'change' }]
}

watch(() => props.visible, (val) => {
  if (val && props.mode === 'edit' && props.record) {
    Object.assign(form, props.record)
  } else if (val) {
    Object.assign(form, emptyForm())
    formRef.value?.resetFields()
  }
})

async function handleSave() {
  if (!formRef.value) return
  try { await formRef.value.validate() } catch { return }
  submitting.value = true
  try {
    emit('save', { ...form })
    emit('update:visible', false)
    ElMessage.success('Saved')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}
</script>
