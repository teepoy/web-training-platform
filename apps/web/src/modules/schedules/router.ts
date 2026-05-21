import type { RouteRecordRaw } from 'vue-router'

export const scheduleRoutes: RouteRecordRaw[] = [
  { path: '/schedules', component: () => import('./views/SchedulesView.vue') },
  { path: '/schedules/:id', component: () => import('./views/ScheduleDetailView.vue') },
]

export const routes = scheduleRoutes
