import type { RouteRecordRaw } from 'vue-router'

export const authRoutes: RouteRecordRaw[] = [
  { path: '/login', component: () => import('./presentation/pages/LoginView.vue') },
  { path: '/register', component: () => import('./presentation/pages/RegisterView.vue') },
  { path: '/auth/oauth/success', component: () => import('./presentation/pages/OAuthCallbackView.vue') },
  { path: '/auth/oauth/register', component: () => import('./presentation/pages/OAuthRegisterView.vue') },
]

export const routes = authRoutes
