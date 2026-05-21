import type { RouteRecordRaw } from 'vue-router'

export const predictionRoutes: RouteRecordRaw[] = [
  { path: '/prediction-jobs', component: () => import('./presentation/pages/PredictionJobsView.vue') },
]

export const routes = predictionRoutes
