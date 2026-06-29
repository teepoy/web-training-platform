import type { RouteRecordRaw } from "vue-router";

export const sandboxRoutes: RouteRecordRaw[] = [
  {
    path: "/sandbox",
    redirect: "/sandbox/rchannel-denoise",
  },
  {
    path: "/sandbox/classify",
    name: "sandbox-classify",
    component: () => import("./presentation/pages/scenarios/classify/ClassifySandboxView.vue"),
  },
  {
    path: "/sandbox/rchannel-denoise",
    name: "sandbox-rchannel-denoise",
    component: () =>
      import("./presentation/pages/scenarios/rchannel-denoise/RChannelDenoiseSandboxView.vue"),
  },
  {
    path: "/sandbox/vxe-table",
    name: "sandbox-vxe-table",
    component: () => import("./presentation/pages/scenarios/vxe-table/VxeTableSandbox.vue"),
  },
];
