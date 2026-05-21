import type { RouteRecordRaw } from 'vue-router'

export const sensorRoutes: RouteRecordRaw[] = [
  { path: '/sensors', component: () => import('./views/SensorsView.vue') },
]

export const routes = sensorRoutes
