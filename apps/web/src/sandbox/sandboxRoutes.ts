import type { RouteRecordRaw } from 'vue-router'

export const sandboxRoutes: RouteRecordRaw[] = [
  {
    path: '/sandbox',
    redirect: '/sandbox/rchannel-denoise',
  },
  {
    path: '/sandbox/classify',
    name: 'sandbox-classify',
    component: () => import('./scenarios/classify/ClassifySandboxView.vue'),
  },
  {
    path: '/sandbox/rchannel-denoise',
    name: 'sandbox-rchannel-denoise',
    component: () => import('./scenarios/rchannel-denoise/RChannelDenoiseSandboxView.vue'),
  },
]
