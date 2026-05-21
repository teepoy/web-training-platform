import type { RouteRecordRaw } from 'vue-router'

export const sensorRoutes: RouteRecordRaw[] = [
  { path: '/sensors', component: () => import('./presentation/pages/SensorsView.vue') },
]

export const routes = sensorRoutes
