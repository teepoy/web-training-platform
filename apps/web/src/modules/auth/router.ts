import type { RouteRecordRaw } from 'vue-router'

export const authRoutes: RouteRecordRaw[] = [
  { path: '/login', component: () => import('./views/LoginView.vue') },
  { path: '/register', component: () => import('./views/RegisterView.vue') },
  { path: '/auth/oauth/success', component: () => import('./views/OAuthCallbackView.vue') },
  { path: '/auth/oauth/register', component: () => import('./views/OAuthRegisterView.vue') },
]

export const routes = authRoutes
