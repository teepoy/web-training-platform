import type { RouteRecordRaw } from 'vue-router'

export const modelRoutes: RouteRecordRaw[] = [
  { path: '/models', component: () => import('./presentation/pages/ModelsView.vue') },
]

export const routes = modelRoutes
