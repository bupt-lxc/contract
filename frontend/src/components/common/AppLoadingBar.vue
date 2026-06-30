<template>
  <Transition name="loading-bar">
    <div v-if="loadingState.count > 0" class="app-loading-bar" />
  </Transition>
</template>

<script setup>
import { loadingState } from '@/api/bridge.js'
</script>

<style scoped>
.app-loading-bar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  z-index: 9999;
  pointer-events: none;
}

.app-loading-bar::after {
  content: '';
  display: block;
  height: 100%;
  width: 100%;
  background: linear-gradient(90deg, transparent, #409eff, transparent);
  animation: loading-slide 1.2s ease-in-out infinite;
}

@keyframes loading-slide {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

.loading-bar-enter-active {
  transition: opacity 0.1s ease 0.1s;
}
.loading-bar-leave-active {
  transition: opacity 0.15s ease;
}
.loading-bar-enter-from,
.loading-bar-leave-to {
  opacity: 0;
}
</style>
