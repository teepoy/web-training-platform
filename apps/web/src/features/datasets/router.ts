import type { RouteRecordRaw } from "vue-router";

export const datasetRoutes: RouteRecordRaw[] = [
  {
    path: "/datasets",
    redirect: (to) => ({
      path: "/library",
      query: { ...to.query, tab: "datasets" },
    }),
  },
  {
    path: "/datasets/:id",
    component: () => import("./presentation/pages/DatasetDetailView.vue"),
  },
];

export const routes = datasetRoutes;
