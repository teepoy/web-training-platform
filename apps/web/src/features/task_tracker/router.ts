import type { RouteRecordRaw } from 'vue-router'

export const taskTrackerRoutes: RouteRecordRaw[] = [
  { path: '/tasks', component: () => import('./presentation/pages/TaskExplorerView.vue') },
]

export const routes = taskTrackerRoutes
