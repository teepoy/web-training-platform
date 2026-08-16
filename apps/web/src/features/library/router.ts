import type { RouteRecordRaw } from "vue-router";

export const libraryRoutes: RouteRecordRaw[] = [
  {
    path: "/library",
    name: "library",
    component: () => import("./presentation/pages/LibraryWorkspaceView.vue"),
  },
];

export const routes = libraryRoutes;
