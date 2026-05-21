import type { RouteRecordRaw } from 'vue-router'

export const scheduleRoutes: RouteRecordRaw[] = [
  { path: '/schedules', component: () => import('./presentation/pages/SchedulesView.vue') },
  { path: '/schedules/:id', component: () => import('./presentation/pages/ScheduleDetailView.vue') },
]

export const routes = scheduleRoutes
