import type { RouteRecordRaw } from 'vue-router'
import SettingsLayout from '@/app/layouts/SettingsLayout.vue'

export const settingsRoutes: RouteRecordRaw[] = [
  {
    path: '/settings',
    component: SettingsLayout,
    children: [
      { path: '', redirect: '/settings/access-keys' },
      { path: 'access-keys', component: () => import('./presentation/pages/SettingsView.vue') },
    ],
  },
]

export const routes = settingsRoutes
