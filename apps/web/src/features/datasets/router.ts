import type { RouteRecordRaw } from 'vue-router'

export const datasetRoutes: RouteRecordRaw[] = [
  { path: '/datasets', component: () => import('./presentation/pages/DatasetListView.vue') },
  {
    path: '/datasets/:id',
    component: () => import('./presentation/pages/DatasetDetailView.vue'),
  },
]

export const routes = datasetRoutes
