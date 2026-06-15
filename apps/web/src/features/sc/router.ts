import type { RouteRecordRaw } from "vue-router";

const compactScWorkspaceMeta = {
  hideAppHeader: true,
  contentPadding: "5px",
  autoCollapseSidebar: true,
};

export const scRoutes: RouteRecordRaw[] = [
  {
    path: "/sc",
    redirect: "/sc/preview",
  },
  {
    path: "/sc/preview",
    name: "sc-preview",
    component: () => import("./presentation/pages/PreviewPage.vue"),
    meta: compactScWorkspaceMeta,
  },
  {
    path: "/sc/preview/:inspectionTime/:waferKey",
    name: "sc-preview-inspection",
    component: () => import("./presentation/pages/PreviewPage.vue"),
    meta: compactScWorkspaceMeta,
  },
  {
    path: "/sc/handbook",
    name: "sc-handbook",
    component: () => import("./presentation/pages/HandbookPage.vue"),
  },
  {
    path: "/datasets/:id/sc/classify",
    name: "sc-reclassify",
    component: () => import("./presentation/pages/ReclassifyPage.vue"),
    meta: compactScWorkspaceMeta,
  },
];
