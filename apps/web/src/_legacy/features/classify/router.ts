import type { RouteRecordRaw } from 'vue-router'

export const classifyRoutes: RouteRecordRaw[] = [
  { path: '/datasets/:id/classify', component: () => import('./presentation/pages/ClassifyView.vue') },
]

export const routes = classifyRoutes
