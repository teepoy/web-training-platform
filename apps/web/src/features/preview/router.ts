import type { RouteRecordRaw } from 'vue-router'

export const previewRoutes: RouteRecordRaw[] = [
  { path: '/preview', name: 'preview-launch', component: () => import('./presentation/pages/PreviewLaunchView.vue') },
  { path: '/preview/:sessionId', name: 'preview-classify', component: () => import('./presentation/pages/PreviewClassifyView.vue') },
]

export const routes = previewRoutes
