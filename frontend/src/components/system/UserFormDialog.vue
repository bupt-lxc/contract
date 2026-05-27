<template>
  <el-dialog
    :model-value="visible"
    :title="mode === 'edit' ? 'Edit User' : 'Add User'"
    width="480px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item label="Machine ID" prop="machine_id">
        <el-input v-model="form.machine_id" :disabled="mode === 'edit'" maxlength="7" />
      </el-form-item>
      <el-form-item label="Name" prop="user_name">
        <el-input v-model="form.user_name" />
      </el-form-item>
      <el-form-item label="Email">
        <el-input v-model="form.email" />
      </el-form-item>
      <el-form-item label="Role" prop="role">
        <el-select v-model="form.role">
          <el-option label="Requester" value="requester" />
          <el-option label="Admin" value="admin" />
        </el-select>
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

const emptyForm = () => ({
  machine_id: '', user_name: '', email: '', role: 'requester'
})

const form = reactive(emptyForm())

const rules = {
  machine_id: [{ required: true, message: 'Machine ID is required', trigger: 'blur' }],
  user_name: [{ required: true, message: 'Name is required', trigger: 'blur' }],
  role: [{ required: true, message: 'Role is required', trigger: 'change' }]
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
