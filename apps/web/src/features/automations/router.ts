import type { RouteRecordRaw } from "vue-router";

export const automationRoutes: RouteRecordRaw[] = [
  {
    path: "/automations",
    name: "automations",
    component: () => import("./presentation/pages/AutomationsView.vue"),
  },
];

export const routes = automationRoutes;
