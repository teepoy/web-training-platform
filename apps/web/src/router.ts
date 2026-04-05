import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: () => import('./views/DashboardView.vue') },
    { path: '/datasets', component: () => import('./views/DatasetsView.vue') },
    { path: '/datasets/:id', component: () => import('./views/DatasetDetailView.vue') },
    { path: '/datasets/:id/classify', component: () => import('./views/ClassifyView.vue') },
    { path: '/jobs', component: () => import('./views/JobsView.vue') },
    { path: '/jobs/:id', component: () => import('./views/JobDetailView.vue') },
    { path: '/predictions', component: () => import('./views/PredictionsView.vue') },
    { path: '/presets', component: () => import('./views/PresetEditorView.vue') },
    { path: '/schedules', component: () => import('./views/SchedulesView.vue') },
    { path: '/schedules/:id', component: () => import('./views/ScheduleDetailView.vue') },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('./views/NotFoundView.vue') },
  ],
})

// NOTE: router.beforeEach runs before the store is initialized in some setups
// Use pinia store lazily inside the callback
router.beforeEach((_to, _from, next) => {
  // TODO: Enable auth guard when OAuth is implemented
  // const authStore = useAuthStore()
  // if (!authStore.isAuthenticated && _to.meta.requiresAuth) { next('/login'); return }
  next() // Always pass through for now
})
