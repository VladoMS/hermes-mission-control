<template>
  <span class="version-badge">v2.0</span>
</template>

<script setup>
// Static version badge — bumped manually with releases.
</script>

<style scoped>
.version-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-faint);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--line-dim);
  border-radius: 12px;
  letter-spacing: 0.08em;
}
</style>
