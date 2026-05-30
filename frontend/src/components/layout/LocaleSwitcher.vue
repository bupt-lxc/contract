<template>
  <div class="locale-switcher">
    <el-switch
      v-model="isZh"
      active-text="中"
      inactive-text="EN"
      inline-prompt
      @change="toggleLocale"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { locale } = useI18n()
const isZh = ref(locale.value === 'zh-CN')

function toggleLocale() {
  locale.value = isZh.value ? 'zh-CN' : 'en-US'
  localStorage.setItem('app-locale', locale.value)
}
</script>

<style scoped>
.locale-switcher {
  display: flex;
  align-items: center;
  margin-right: 12px;
}
</style>
