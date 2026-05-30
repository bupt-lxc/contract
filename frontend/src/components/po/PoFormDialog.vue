<template>
  <el-dialog
    :model-value="visible"
    :title="mode === 'edit' ? $t('po.editPo') : $t('po.addPo')"
    width="520px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-row :gutter="16">
        <el-col :span="24">
          <el-form-item :label="$t('po.poNo')">
            <el-input v-model="form.po_no" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="$t('po.vendor')" prop="vendor_id">
        <el-select v-model="form.vendor_id" filterable>
          <el-option v-for="v in vendors" :key="v.vendor_id" :label="`${v.vendor_name} — KSRM: ${v.ksrm_vendor_code || '-'}`" :value="v.vendor_id" />
        </el-select>
      </el-form-item>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('po.poAmount')">
            <el-input-number v-model="form.po_amount" :precision="2" :min="0" controls-position="right" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('po.contractNo')">
            <el-input v-model="form.contract_no" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('po.contractFrom')">
            <el-date-picker v-model="form.contract_from" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('po.contractTo')">
            <el-date-picker v-model="form.contract_to" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="$t('po.paymentFrequency')">
        <el-input v-model="form.payment_frequency" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)" :disabled="submitting">{{ $t('common.cancel') }}</el-button>
      <el-button type="primary" @click="handleSave" :loading="submitting">{{ $t('common.save') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'

const props = defineProps({
  visible: Boolean,
  mode: { type: String, default: 'create' },
  record: Object,
  vendors: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:visible', 'save'])

const { t } = useI18n()

const formRef = ref()
const submitting = ref(false)

const emptyForm = () => ({
  po_no: '', vendor_id: '', po_amount: null,
  contract_from: null, contract_to: null, contract_no: '', payment_frequency: ''
})

const form = reactive(emptyForm())

const rules = {
  vendor_id: [{ required: true, message: t('po.vendorRequired'), trigger: 'change' }],
  po_amount: [{ required: true, message: t('po.poAmountRequired'), trigger: 'blur' }]
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
    ElMessage.success(t('po.saved'))
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}
</script>
