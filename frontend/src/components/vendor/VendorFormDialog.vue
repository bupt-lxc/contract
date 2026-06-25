<template>
  <el-dialog
    :model-value="visible"
    :title="mode === 'edit' ? $t('vendor.editVendor') : $t('vendor.addVendor')"
    width="520px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-alert
      v-if="mode === 'edit'"
      :title="$t('vendor.editSyncNotice')"
      type="warning"
      show-icon
      :closable="false"
      style="margin-bottom:16px"
    />
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-row :gutter="16">
        <el-col :span="12" v-if="mode === 'edit'">
          <el-form-item :label="$t('vendor.vendorId')" prop="vendor_id">
            <el-input v-model="form.vendor_id" disabled />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="mode === 'create' ? $t('vendor.vendorNameFull') : $t('vendor.vendorName')" prop="vendor_name">
            <el-input v-model="form.vendor_name" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('vendor.companyNameCn')">
            <el-input v-model="form.company_name_cn" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="$t('vendor.serviceScope')" prop="service_scope">
        <el-select v-model="form.service_scope" filterable>
          <el-option v-for="s in serviceScopes" :key="s" :label="s" :value="s" />
        </el-select>
      </el-form-item>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('vendor.ksrmCode')">
            <el-input v-model="form.ksrm_vendor_code" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('vendor.contactPerson')">
            <el-input v-model="form.contact_person" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('vendor.phone')">
            <el-input v-model="form.phone" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('vendor.email')">
            <el-input v-model="form.email" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="$t('vendor.description')">
        <el-input v-model="form.description" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item :label="$t('vendor.inquiryHistory')">
        <el-input v-model="form.inquiry_history" type="textarea" :rows="2" />
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
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useVendor } from '@/composables/useVendor.js'

const props = defineProps({
  visible: Boolean,
  mode: { type: String, default: 'create' },
  record: Object
})

const emit = defineEmits(['update:visible', 'save'])
const { t } = useI18n()
const { checkKsrmDuplicate } = useVendor()

const formRef = ref()
const submitting = ref(false)

const serviceScopes = [
  'Transportation', 'engineering Service', 'Equipment', 'Parts', 'Driver',
  'Test car rental', 'General Service', 'Dealers', 'Import&Export&cusoms clearance',
  'Insurance', 'Harness', 'Maintenance', 'Security', 'Testing support', 'Others'
]

const emptyForm = () => ({
  vendor_id: '', vendor_name: '', company_name_cn: '', service_scope: '',
  ksrm_vendor_code: '', contact_person: '', phone: '', email: '',
  description: '', inquiry_history: ''
})

const form = reactive(emptyForm())

const rules = {
  vendor_name: [{ required: true, message: t('vendor.vendorNameRequired'), trigger: 'blur' }],
  service_scope: [{ required: true, message: t('vendor.serviceScopeRequired'), trigger: 'change' }]
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

  // KSRM duplicate check on create
  if (props.mode === 'create' && form.ksrm_vendor_code && form.ksrm_vendor_code.trim()) {
    try {
      const duplicate = await checkKsrmDuplicate(form.ksrm_vendor_code.trim())
      if (duplicate) {
        await ElMessageBox.confirm(
          t('vendor.ksrmDuplicateMessage', { code: form.ksrm_vendor_code, name: duplicate.vendor_name }),
          t('vendor.ksrmDuplicateTitle'),
          { confirmButtonText: t('common.confirmAdd'), cancelButtonText: t('common.cancel'), type: 'warning' }
        )
      }
    } catch (e) {
      // User cancelled or API error
      if (e === 'cancel' || e === 'close') return
      ElMessage.error(e.message)
      return
    }
  }

  submitting.value = true
  try {
    emit('save', { ...form })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}
</script>
