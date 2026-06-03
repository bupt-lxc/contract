<template>
  <el-dialog
    :model-value="visible"
    :title="mode === 'edit' ? $t('gr.editGr') : $t('gr.addGr')"
    width="600px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-row :gutter="16">
        <el-col :span="24">
          <el-form-item :label="$t('gr.requester')" prop="requester_id">
            <el-select v-model="form.requester_id" filterable :disabled="isReadOnly">
              <el-option v-for="u in availableUsers" :key="u.user_id" :label="`${u.user_name} — ${u.machine_id}`" :value="u.user_id" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="24">
          <el-form-item :label="$t('gr.grNo')">
            <el-input v-model="form.gr_no" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('gr.estimatedAmount')">
            <el-input-number v-model="form.estimated_amount" :precision="2" :min="0" controls-position="right" style="width:100%" :disabled="isReadOnly" @change="calcInclTax" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('gr.taxRate')">
            <el-input-number v-model="form.tax_rate" :precision="2" :min="0" :max="100" controls-position="right" style="width:100%" @change="calcInclTax" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('gr.conValue')">
            <el-input-number v-if="isApproved" v-model="form.con_value" :precision="2" :min="0" controls-position="right" style="width:100%" />
            <el-input-number v-else :model-value="computedInclTax" :precision="2" :min="0" controls-position="right" style="width:100%" disabled />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="24">
          <el-form-item :label="$t('gr.goodsServiceDescription')">
            <el-input v-model="form.goods_service_description" type="textarea" :rows="2" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('gr.confirmationName')">
            <el-input v-model="form.confirmation_name" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('gr.lastDelivery')">
            <el-switch
              v-model="form.last_delivery"
              active-value="Y"
              inactive-value="N"
              :active-text="$t('common.confirm')"
              :inactive-text="$t('common.cancel')"
            />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('gr.deliveryFrom')">
            <el-date-picker v-model="form.delivery_from" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('gr.deliveryTo')">
            <el-date-picker v-model="form.delivery_to" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="$t('gr.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="3" />
      </el-form-item>
      <el-row v-if="mode === 'edit' && !isReadOnly" :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('gr.pendingDate')">
            <el-date-picker v-model="form.pending_date" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('gr.approvedDate')">
            <el-date-picker v-model="form.approved_date" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
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
      <el-button type="primary" @click="handleSave" :loading="submitting">{{ $t('common.save') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Paperclip } from '@element-plus/icons-vue'
import { callApi } from '@/api/bridge.js'
import { ElMessage } from 'element-plus'

const { t } = useI18n()

const props = defineProps({
  visible: Boolean,
  mode: { type: String, default: 'create' },
  record: Object,
  users: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:visible', 'save'])

const currentUser = computed(() => window.__currentUser || {})
const isAdmin = computed(() => currentUser.value?.role === 'admin')

// Some fields are read-only for approved / manager_confirm GRs (backend limits allowed keys)
const isReadOnly = computed(() => {
  if (props.mode !== 'edit') return false
  const status = props.record?.status
  return status === 'manager_confirm' || status === 'approved'
})

const isApproved = computed(() => {
  return props.mode === 'edit' && props.record?.status === 'approved'
})

// Non-admin users can only select themselves as requester
const availableUsers = computed(() => {
  if (isAdmin.value) return props.users
  return props.users.filter(u => u.user_id === currentUser.value?.user_id)
})

const formRef = ref()
const submitting = ref(false)
const pickedFiles = ref([])

const emptyForm = () => ({
  gr_no: null, requester_id: '', estimated_amount: null, tax_rate: null, con_value: null, remark: '',
  pending_date: null, approved_date: null,
  goods_service_description: '', confirmation_name: '', delivery_from: null, delivery_to: null, last_delivery: 'N'
})

const form = reactive(emptyForm())

// Auto-calculate tax-included amount: amount_excl_tax × (1 + tax_rate / 100)
const computedInclTax = computed(() => {
  const amount = form.estimated_amount
  const rate = form.tax_rate
  if (amount == null || amount === '' || rate == null || rate === '') return null
  const a = Number(amount)
  const r = Number(rate)
  if (isNaN(a) || isNaN(r)) return null
  return Math.round((a * (1 + r / 100)) * 100) / 100
})

function calcInclTax() {
  form.con_value = computedInclTax.value
}

const rules = {
  requester_id: [{ required: true, message: t('gr.requesterRequired'), trigger: 'blur' }],
  estimated_amount: [{ required: true, message: t('gr.estimatedAmountRequired'), trigger: 'blur' }]
}

watch(() => props.visible, (val) => {
  if (val) {
    pickedFiles.value = []
    if (props.mode === 'edit' && props.record) {
      Object.assign(form, props.record)
    } else {
      Object.assign(form, emptyForm())
      // Auto-set requester for non-admin users
      if (!isAdmin.value) {
        form.requester_id = currentUser.value?.user_id || ''
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
