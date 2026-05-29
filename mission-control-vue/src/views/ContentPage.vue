<template>
  <div class="content-page section">
    <div class="section-head">
      <div class="title-block">
        <div class="eyebrow">CONTENT</div>
        <div class="display medium">{{ docCount }} AGENT · {{ vaultCount }} VAULT</div>
      </div>
    </div>

    <div class="content-layout">
      <ContentSidebar class="content-sidebar" />
      <ContentPreview class="content-main" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useContentStore } from '../stores/content.js'
import ContentSidebar from '../components/ContentSidebar.vue'
import ContentPreview from '../components/ContentPreview.vue'

const contentStore = useContentStore()
const docCount = computed(() => contentStore.documentCount)
const vaultCount = computed(() => contentStore.vaultCount)
</script>

<style scoped>
.content-page { position: relative; z-index: 5; }
.content-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 20px;
  align-items: start;
}
.content-main { min-width: 0; overflow: hidden; }
@media (max-width: 900px) {
  .content-layout { grid-template-columns: 1fr; }
}
</style>
