<template>
  <el-dialog
    :model-value="visible"
    :title="mode === 'edit' ? 'Edit PO' : 'Add PO'"
    width="520px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="PO ID" prop="po_id">
            <el-input v-model="form.po_id" :disabled="mode === 'edit'" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="PO No">
            <el-input v-model="form.po_no" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="Vendor" prop="vendor_id">
        <el-select v-model="form.vendor_id" filterable>
          <el-option v-for="v in vendors" :key="v.vendor_id" :label="`${v.vendor_name} — KSRM: ${v.ksrm_vendor_code || '-'}`" :value="v.vendor_id" />
        </el-select>
      </el-form-item>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="PO Amount">
            <el-input-number v-model="form.po_amount" :precision="2" :min="0" controls-position="right" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="Contract No">
            <el-input v-model="form.contract_no" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="Contract From">
            <el-date-picker v-model="form.contract_from" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="Contract To">
            <el-date-picker v-model="form.contract_to" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="Payment Frequency">
        <el-input v-model="form.payment_frequency" />
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
  record: Object,
  vendors: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:visible', 'save'])

const formRef = ref()
const submitting = ref(false)

const emptyForm = () => ({
  po_id: '', po_no: '', vendor_id: '', po_amount: null,
  contract_from: null, contract_to: null, contract_no: '', payment_frequency: ''
})

const form = reactive(emptyForm())

const rules = {
  po_id: [{ required: true, message: 'PO ID is required', trigger: 'blur' }],
  vendor_id: [{ required: true, message: 'Vendor is required', trigger: 'change' }]
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
