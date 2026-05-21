import type { RouteRecordRaw } from 'vue-router'

export const previewRoutes: RouteRecordRaw[] = [
  { path: '/preview', name: 'preview-launch', component: () => import('./views/PreviewLaunchView.vue') },
  { path: '/preview/:sessionId', name: 'preview-classify', component: () => import('./views/PreviewClassifyView.vue') },
]

export const routes = previewRoutes
