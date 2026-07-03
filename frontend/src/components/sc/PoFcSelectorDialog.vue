<template>
  <el-dialog v-model="visible" :title="$t('sc.newCalloffSc')" width="700px">
    <el-table :data="fcPos" @row-click="select" highlight-current-row style="cursor: pointer">
      <el-table-column prop="po_id" :label="$t('po.poId')" width="200" />
      <el-table-column prop="po_no" :label="$t('po.poNo')" width="150" />
      <el-table-column prop="vendor_name" :label="$t('po.vendorName')" width="150" />
      <el-table-column prop="po_amount" :label="$t('po.poAmount')" width="130">
        <template #default="{ row }">
          <AmountDisplay :value="row.po_amount" />
        </template>
      </el-table-column>
      <el-table-column prop="open_po_amount" :label="$t('po.openPoAmountFc')" width="130">
        <template #default="{ row }">
          <AmountDisplay :value="row.open_po_amount" />
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { usePo } from '@/composables/usePo.js'
import AmountDisplay from '@/components/common/AmountDisplay.vue'

const { state, searchPos } = usePo()

const visible = defineModel('visible', { type: Boolean, default: false })
const emit = defineEmits(['select'])

const fcPos = ref([])

watch(visible, async (val) => {
  if (val) {
    await searchPos(null, { is_fc_po: '1', status: 'active' })
    fcPos.value = state.rows
  }
})

function select(row) {
  emit('select', row)
  visible.value = false
}
</script>
