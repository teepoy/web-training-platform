import type { RouteRecordRaw } from 'vue-router'

export const predictionRoutes: RouteRecordRaw[] = [
  { path: '/prediction-jobs', component: () => import('./views/PredictionJobsView.vue') },
]

export const routes = predictionRoutes
