<template>
  <el-dialog
    :model-value="visible"
    :title="mode === 'edit' ? $t('user.editUser') : $t('user.addUser')"
    width="480px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item :label="$t('user.machineId')" prop="machine_id">
        <el-input v-model="form.machine_id" :disabled="mode === 'edit'" maxlength="7" />
      </el-form-item>
      <el-form-item :label="$t('user.name')" prop="user_name">
        <el-input v-model="form.user_name" />
      </el-form-item>
      <el-form-item :label="$t('user.email')">
        <el-input v-model="form.email" />
      </el-form-item>
      <el-form-item :label="$t('user.role')" prop="role">
        <el-select v-model="form.role">
          <el-option :label="$t('role.Requester')" value="requester" />
          <el-option :label="$t('role.Admin')" value="admin" />
        </el-select>
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

const { t } = useI18n()

const props = defineProps({
  visible: Boolean,
  mode: { type: String, default: 'create' },
  record: Object
})

const emit = defineEmits(['update:visible', 'save'])

const formRef = ref()
const submitting = ref(false)

const emptyForm = () => ({
  machine_id: '', user_name: '', email: '', role: 'requester'
})

const form = reactive(emptyForm())

const rules = {
  machine_id: [{ required: true, message: () => t('user.machineIdRequired'), trigger: 'blur' }],
  user_name: [{ required: true, message: () => t('user.nameRequired'), trigger: 'blur' }],
  role: [{ required: true, message: () => t('user.roleRequired'), trigger: 'change' }]
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
