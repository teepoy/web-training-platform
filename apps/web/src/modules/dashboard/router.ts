import type { RouteRecordRaw } from 'vue-router'

export const dashboardRoutes: RouteRecordRaw[] = [
  { path: '/dashboard', component: () => import('./views/DashboardView.vue') },
]

export const routes = dashboardRoutes
