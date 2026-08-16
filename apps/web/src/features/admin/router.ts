import type { RouteRecordRaw } from "vue-router";

export const adminRoutes: RouteRecordRaw[] = [
  {
    path: "infrastructure",
    component: () => import("./presentation/pages/AdminInfrastructureView.vue"),
  },
];

export const routes = adminRoutes;
