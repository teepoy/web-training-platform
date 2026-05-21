import type { RouteRecordRaw } from 'vue-router'

export const trainingRoutes: RouteRecordRaw[] = [
  { path: '/jobs', component: () => import('./presentation/pages/TrainingJobsView.vue') },
  { path: '/jobs/:id', component: () => import('./presentation/pages/JobDetailView.vue') },
]

export const routes = trainingRoutes
