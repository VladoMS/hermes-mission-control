<template>
  <div class="profiles-page section">
    <div class="section-head">
      <div class="title-block">
        <div class="eyebrow">PROFILES</div>
        <div class="display medium">{{ profiles.length }} AGENT PROFILES</div>
      </div>
      <div class="filter-chips">
        <button class="chip" :class="{ red: filter === 'all' }" @click="filter = 'all'">ALL</button>
        <button class="chip" :class="{ green: filter === 'active' }" @click="filter = 'active'">ACTIVE</button>
        <button class="chip" :class="{ amber: filter === 'idle' }" @click="filter = 'idle'">IDLE</button>
        <button class="chip" :class="{ cyan: filter === 'dormant' }" @click="filter = 'dormant'">DORMANT</button>
      </div>
    </div>

    <div class="profiles-grid">
      <ProfileCard
        v-for="p in filteredProfiles"
        :key="p.name"
        :profile="p"
      />
    </div>

    <ActivityLogTable class="profiles-log" />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useProfilesStore } from '../stores/profiles.js'
import ProfileCard from '../components/ProfileCard.vue'
import ActivityLogTable from '../components/ActivityLogTable.vue'

const profilesStore = useProfilesStore()
const profiles = computed(() => profilesStore.profiles)
const filter = ref('all')

const filteredProfiles = computed(() => {
  const all = profiles.value
  if (filter.value === 'all') return all
  return all.filter(p => profilesStore.getStatus(p) === filter.value)
})
</script>

<style scoped>
.profiles-page { position: relative; z-index: 5; }
.filter-chips { display: flex; gap: 6px; }
.filter-chips .chip { cursor: pointer; }
.profiles-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
  margin-bottom: 28px;
}
.profiles-log { margin-top: 28px; }
@media (max-width: 720px) {
  .profiles-grid { grid-template-columns: 1fr; }
}
</style>
