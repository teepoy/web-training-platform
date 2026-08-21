import { createRouter, createWebHistory } from "vue-router";
import { getStoredToken } from "@/features/auth/application/store";
import { useAuthStore } from "@/features/auth/application/store";
import { sandboxRoutes } from "@/features/sandbox/router";
import AdminLayout from "@/app/layouts/AdminLayout.vue";
import SettingsLayout from "@/app/layouts/SettingsLayout.vue";
import { adminRoutes } from "@/features/admin/router";
import { automationRoutes } from "@/features/automations/router";
import { authRoutes } from "@/features/auth/router";
import { dashboardRoutes } from "@/features/dashboard/router";
import { datasetRoutes } from "@/features/datasets/router";
import { datasetCollectionRoutes } from "@/features/dataset-collections/router";
import { libraryRoutes } from "@/features/library/router";
import { modelRoutes } from "@/features/models/router";
import { predictionRoutes } from "@/features/prediction/router";
import { scRoutes } from "@/features/sc/router";
import { taskTrackerRoutes } from "@/features/task_tracker/router";
import { trainingRoutes } from "@/features/training/router";

const AUTH_ROUTES = ["/login", "/register", "/auth/oauth/success", "/auth/oauth/register"];

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/sc/preview" },
    ...authRoutes,
    ...dashboardRoutes,
    ...taskTrackerRoutes,
    ...automationRoutes,
    ...libraryRoutes,
    ...datasetRoutes,
    ...datasetCollectionRoutes,
    ...modelRoutes,
    ...trainingRoutes,
    ...predictionRoutes,
    ...scRoutes,
    {
      path: "/admin",
      component: AdminLayout,
      children: [
        { path: "", redirect: "/admin/dashboard" },
        {
          path: "dashboard",
          component: () => import("@/features/dashboard/presentation/pages/DashboardView.vue"),
        },
        ...adminRoutes,
      ],
    },
    {
      path: "/settings",
      component: SettingsLayout,
      children: [
        { path: "", redirect: "/settings/access-keys" },
        {
          path: "access-keys",
          component: () => import("@/features/settings/presentation/pages/SettingsView.vue"),
        },
      ],
    },
    ...(import.meta.env.DEV ? sandboxRoutes : []),
    { path: "/:pathMatch(.*)*", name: "not-found", redirect: "/sc/preview" },
  ],
});

router.beforeEach((to) => {
  const authStore = useAuthStore();
  const token = getStoredToken();
  const isAuthRoute = AUTH_ROUTES.includes(to.path);

  if (to.path.startsWith("/admin") && !authStore.user?.is_superadmin) {
    return "/library";
  }

  if (isAuthRoute && token) {
    return "/library";
  }

  if (!isAuthRoute && !token) {
    return "/login";
  }

  return true;
});
