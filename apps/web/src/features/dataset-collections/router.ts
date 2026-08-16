import type { RouteRecordRaw } from "vue-router";

const compactCollectionWorkspaceMeta = {
  hideAppHeader: true,
  contentPadding: "5px",
  autoCollapseSidebar: true,
};

export const datasetCollectionRoutes: RouteRecordRaw[] = [
  {
    path: "/dataset-collections",
    name: "dataset-collections",
    redirect: (to) => ({
      path: "/library",
      query: { ...to.query, tab: "collections" },
    }),
  },
  {
    path: "/dataset-collections/:collectionId",
    name: "dataset-collection-detail",
    component: () => import("./presentation/pages/DatasetCollectionDetailView.vue"),
  },
  {
    path: "/dataset-collections/:collectionId/classify/:id",
    name: "dataset-collection-classify",
    component: () => import("./presentation/pages/CollectionClassifyView.vue"),
    meta: compactCollectionWorkspaceMeta,
  },
];

export const routes = datasetCollectionRoutes;
