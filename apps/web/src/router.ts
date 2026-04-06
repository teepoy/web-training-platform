import { createRouter, createWebHistory } from 'vue-router'

const AUTH_ROUTES = ['/login', '/register']

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/login', component: () => import('./views/LoginView.vue') },
    { path: '/register', component: () => import('./views/RegisterView.vue') },
    { path: '/dashboard', component: () => import('./views/DashboardView.vue') },
    { path: '/datasets', component: () => import('./views/DatasetsView.vue') },
    { path: '/datasets/:id', component: () => import('./views/DatasetDetailView.vue') },
    { path: '/datasets/:id/classify', component: () => import('./views/ClassifyView.vue') },
    { path: '/jobs', component: () => import('./views/JobsView.vue') },
    { path: '/jobs/:id', component: () => import('./views/JobDetailView.vue') },
    { path: '/presets', component: () => import('./views/PresetEditorView.vue') },
    { path: '/schedules', component: () => import('./views/SchedulesView.vue') },
    { path: '/schedules/:id', component: () => import('./views/ScheduleDetailView.vue') },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('./views/NotFoundView.vue') },
  ],
})

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('auth_token')
  const isAuthRoute = AUTH_ROUTES.includes(to.path)

  if (isAuthRoute && token) {
    next('/datasets')
    return
  }

  if (!isAuthRoute && !token) {
    next('/login')
    return
  }

  next()
})
