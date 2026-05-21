import type { RouteRecordRaw } from 'vue-router'

export const datasetRoutes: RouteRecordRaw[] = [
  { path: '/datasets', component: () => import('./views/DatasetListView.vue') },
  { path: '/datasets/:id', component: () => import('./views/DatasetDetailView.vue') },
]

export const routes = datasetRoutes
