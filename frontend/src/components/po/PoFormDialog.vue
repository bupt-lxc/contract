<template>
  <el-dialog
    :model-value="visible"
    :title="mode === 'edit' ? $t('po.editPo') : $t('po.addPo')"
    width="520px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('po.poNo')">
            <el-input v-model="form.po_no" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('po.contractPos')">
            <el-input v-model="form.contract_pos" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('po.contractType')">
            <el-select v-model="form.contract_type" clearable>
              <el-option label="PO" value="PO" />
              <el-option label="Contract" value="Contract" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('po.purchaser')">
            <el-input v-model="form.purchaser" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="$t('po.vendor')" prop="vendor_id">
        <el-select v-model="form.vendor_id" filterable>
          <el-option v-for="v in vendors" :key="v.vendor_id" :label="`${v.service_scope} —— ${v.vendor_name} | ${v.vendor_id}`" :value="v.vendor_id" />
        </el-select>
      </el-form-item>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('po.poAmount')" prop="po_amount">
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
          <el-form-item :label="$t('po.contractFrom')" prop="contract_from">
            <el-date-picker v-model="form.contract_from" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('po.contractTo')" prop="contract_to">
            <el-date-picker v-model="form.contract_to" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('po.costCenter')">
            <el-input v-model="form.cost_center" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('po.paymentFrequency')">
            <el-input v-model="form.payment_frequency" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row v-if="mode === 'edit'" :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('po.activingDate')">
            <el-date-picker v-model="form.activing_date" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
      </el-row>
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
      <el-button v-if="mode === 'create'" @click="handleSaveDraft" :disabled="submitting">{{ $t('common.saveDraft') }}</el-button>
      <el-button type="primary" @click="handleSave" :loading="submitting">
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

const props = defineProps({
  visible: Boolean,
  mode: { type: String, default: 'create' },
  record: Object,
  vendors: { type: Array, default: () => [] },
  scRecord: { type: Object, default: null }
})

const emit = defineEmits(['update:visible', 'save', 'save-draft'])

const { t } = useI18n()

const formRef = ref()
const submitting = ref(false)
const pickedFiles = ref([])

const emptyForm = () => ({
  po_no: '', vendor_id: '', po_amount: null,
  contract_from: null, contract_to: null, contract_no: '', payment_frequency: '',
  contract_pos: '', contract_type: '', cost_center: '', purchaser: '',
  activing_date: null
})

const form = reactive(emptyForm())

const rules = {
  vendor_id: [{ required: true, message: t('po.vendorRequired'), trigger: 'change' }],
  po_amount: [{ required: true, message: t('po.poAmountRequired'), trigger: 'blur' }],
  contract_from: [{ required: true, message: t('po.contractFromRequired'), trigger: 'change' }],
  contract_to: [{ required: true, message: t('po.contractToRequired'), trigger: 'change' }]
}

watch(() => props.visible, (val) => {
  if (val) {
    pickedFiles.value = []
    if (props.mode === 'edit' && props.record) {
      Object.assign(form, props.record)
    } else {
      Object.assign(form, emptyForm())
      if (props.scRecord?.cost_center) {
        form.cost_center = String(props.scRecord.cost_center)
      }
      formRef.value?.resetFields()
    }
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

async function handleSaveDraft() {
  // Draft doesn't require field validation
  submitting.value = true
  try {
    emit('save-draft', { ...form, _attachments: pickedFiles.value.map(f => f.path) })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}

async function handleSave() {
  if (!formRef.value) return
  try { await formRef.value.validate() } catch { return }
  submitting.value = true
  try {
    emit('save', { ...form, _attachments: pickedFiles.value.map(f => f.path) })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}
</script>
