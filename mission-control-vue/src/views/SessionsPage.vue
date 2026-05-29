<template>
  <div class="sessions-page section">
    <div class="section-head">
      <div class="title-block">
        <div class="eyebrow">SESSIONS</div>
        <div class="display medium">{{ sessionCount }} SESSIONS</div>
      </div>
    </div>

    <TokenLedger />
    <DailyCostChart />
    <PieChart />
    <SessionsTable />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSessionsStore } from '../stores/sessions.js'
import TokenLedger from '../components/TokenLedger.vue'
import DailyCostChart from '../components/DailyCostChart.vue'
import PieChart from '../components/PieChart.vue'
import SessionsTable from '../components/SessionsTable.vue'

const sessionsStore = useSessionsStore()
const sessionCount = computed(() => sessionsStore.sessionCount)
</script>

<style scoped>
.sessions-page { position: relative; z-index: 5; }
</style>
