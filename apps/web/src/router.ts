import { createRouter, createWebHistory } from 'vue-router'
import { getStoredToken } from './stores/auth'
import { useAuthStore } from './stores/auth'

const AUTH_ROUTES = ['/login', '/register', '/auth/oauth/success', '/auth/oauth/register']

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/login', component: () => import('./views/LoginView.vue') },
    { path: '/register', component: () => import('./views/RegisterView.vue') },
    { path: '/auth/oauth/success', component: () => import('./views/OAuthCallbackView.vue') },
    { path: '/auth/oauth/register', component: () => import('./views/OAuthRegisterView.vue') },
    { path: '/dashboard', component: () => import('./views/DashboardView.vue') },
    { path: '/tasks', component: () => import('./views/TaskExplorerView.vue') },
    { path: '/datasets', component: () => import('./views/DatasetsView.vue') },
    { path: '/datasets/:id', component: () => import('./views/DatasetDetailView.vue') },
    { path: '/datasets/:id/classify', component: () => import('./views/ClassifyView.vue') },
    { path: '/jobs', component: () => import('./views/JobsView.vue') },
    { path: '/jobs/:id', component: () => import('./views/JobDetailView.vue') },
    { path: '/models', component: () => import('./views/ModelsView.vue') },
    { path: '/presets', component: () => import('./views/PresetEditorView.vue') },
    { path: '/schedules', component: () => import('./views/SchedulesView.vue') },
    { path: '/schedules/:id', component: () => import('./views/ScheduleDetailView.vue') },
    { path: '/preview', name: 'preview-launch', component: () => import('./views/PreviewLaunchView.vue') },
    { path: '/preview/:sessionId', name: 'preview-classify', component: () => import('./views/PreviewClassifyView.vue') },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('./views/NotFoundView.vue') },
  ],
})

router.beforeEach((to) => {
  const authStore = useAuthStore()
  const token = getStoredToken()
  const isAuthRoute = AUTH_ROUTES.includes(to.path)

  if (!authStore.authEnabled) {
    if (isAuthRoute) {
      return '/datasets'
    }
    return true
  }

  if (isAuthRoute && token) {
    return '/datasets'
  }

  if (!isAuthRoute && !token) {
    return '/login'
  }

  return true
})
