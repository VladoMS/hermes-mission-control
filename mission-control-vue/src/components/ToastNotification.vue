<template>
  <Teleport to="body">
    <div class="toast-stack">
      <TransitionGroup name="toast">
        <div v-for="t in toasts" :key="t.id" class="toast-item">
          <span class="toast-dot">◆</span>
          <span class="toast-msg mono">{{ t.message }}</span>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup>
import { useToast } from '../composables/useToast.js'
const { toasts } = useToast()
</script>

<style scoped>
.toast-stack {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 999;
  display: flex;
  flex-direction: column;
  gap: 6px;
  pointer-events: none;
}
.toast-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: var(--bg-elevated);
  border: 1px solid var(--line-strong);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
  pointer-events: auto;
}
.toast-dot {
  color: var(--green);
  font-size: 8px;
  flex-shrink: 0;
}
.toast-msg {
  font-size: 11px;
  color: var(--text);
  letter-spacing: 0.06em;
}

/* Transition */
.toast-enter-active { transition: all 0.25s ease-out; }
.toast-leave-active { transition: all 0.2s ease-in; }
.toast-enter-from { opacity: 0; transform: translateX(30px); }
.toast-leave-to { opacity: 0; transform: translateX(30px); }
</style>
