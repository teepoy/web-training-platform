import type { RouteRecordRaw } from 'vue-router'

export const sandboxRoutes: RouteRecordRaw[] = [
  {
    path: '/sandbox',
    redirect: '/sandbox/classify',
  },
  {
    path: '/sandbox/classify',
    name: 'sandbox-classify',
    component: () => import('./scenarios/classify/ClassifySandboxView.vue'),
  },
]
