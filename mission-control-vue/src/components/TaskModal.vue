<template>
  <Teleport to="body">
    <div v-if="task" class="modal-overlay" @click.self="$emit('close')">
      <div class="task-modal panel panel-glow">
        <div class="modal-header">
          <span class="eyebrow">TASK DETAIL</span>
          <button class="modal-close" @click="$emit('close')">✕</button>
        </div>
        <div class="modal-body">
          <div class="modal-field">
            <div class="field-label">ID</div>
            <div class="field-value mono">{{ task.id }}</div>
          </div>
          <div class="modal-field">
            <div class="field-label">TITLE</div>
            <div class="field-value">{{ task.title || task.id }}</div>
          </div>
          <div class="modal-field" v-if="task.body">
            <div class="field-label">BODY</div>
            <pre class="field-body">{{ task.body }}</pre>
          </div>
          <div class="modal-grid">
            <div class="modal-field">
              <div class="field-label">STATUS</div>
              <div class="field-value">{{ task.status }}</div>
            </div>
            <div class="modal-field">
              <div class="field-label">PRIORITY</div>
              <div class="field-value">P{{ task.priority || 0 }}</div>
            </div>
            <div class="modal-field">
              <div class="field-label">ASSIGNEE</div>
              <div class="field-value">{{ task.assignee || '--' }}</div>
            </div>
            <div class="modal-field">
              <div class="field-label">CREATED</div>
              <div class="field-value mono">{{ task.created_at ? new Date(task.created_at * 1000).toISOString().slice(0, 19).replace('T', ' ') : '--' }}</div>
            </div>
          </div>
          <div class="modal-field" v-if="task.result">
            <div class="field-label">RESULT</div>
            <pre class="field-body">{{ task.result }}</pre>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
defineProps({
  task: { type: Object, default: null },
})
defineEmits(['close'])
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.task-modal {
  width: 100%;
  max-width: 600px;
  max-height: 80vh;
  overflow-y: auto;
  background: var(--bg-surface);
  padding: 24px;
}
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.modal-close {
  background: transparent;
  border: 1px solid var(--line);
  color: var(--text-dim);
  width: 28px;
  height: 28px;
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.modal-close:hover { color: var(--text-hi); border-color: var(--line-strong); }
.modal-field { margin-bottom: 12px; }
.field-label {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.15em;
  color: var(--text-faint);
  text-transform: uppercase;
  margin-bottom: 2px;
}
.field-value { font-family: var(--font-body); font-size: 13px; color: var(--text); }
.field-body {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-dim);
  background: var(--bg-deep);
  padding: 10px;
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
}
.modal-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
</style>
