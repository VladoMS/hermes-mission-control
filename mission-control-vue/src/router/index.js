import { createRouter, createWebHistory } from 'vue-router'
import OverviewPage from '../views/OverviewPage.vue'

const routes = [
  { path: '/', name: 'overview', component: OverviewPage },
  { path: '/profiles', name: 'profiles', component: () => import('../views/ProfilesPage.vue') },
  { path: '/kanban', name: 'kanban', component: () => import('../views/KanbanPage.vue') },
  { path: '/servers', name: 'servers', component: () => import('../views/ServersPage.vue') },
  { path: '/sessions', name: 'sessions', component: () => import('../views/SessionsPage.vue') },
  { path: '/content', name: 'content', component: () => import('../views/ContentPage.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
