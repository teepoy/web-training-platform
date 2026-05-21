import type { RouteRecordRaw } from 'vue-router'
import SettingsLayout from '@/layouts/SettingsLayout.vue'

export const settingsRoutes: RouteRecordRaw[] = [
  {
    path: '/settings',
    component: SettingsLayout,
    children: [
      { path: '', redirect: '/settings/access-keys' },
      { path: 'access-keys', component: () => import('./views/SettingsView.vue') },
    ],
  },
]

export const routes = settingsRoutes
