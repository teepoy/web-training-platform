import type { RouteRecordRaw } from 'vue-router'

export const trainingRoutes: RouteRecordRaw[] = [
  { path: '/jobs', component: () => import('./views/TrainingJobsView.vue') },
  { path: '/jobs/:id', component: () => import('./views/JobDetailView.vue') },
]

export const routes = trainingRoutes
