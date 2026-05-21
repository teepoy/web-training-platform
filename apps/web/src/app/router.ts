import { createRouter, createWebHistory } from "vue-router";
import { getStoredToken } from '@/features/auth/application/store';
import { useAuthStore } from '@/features/auth/application/store';
import { sandboxRoutes } from "../sandbox/sandboxRoutes";
import AdminLayout from "../layouts/AdminLayout.vue";
import SettingsLayout from "../layouts/SettingsLayout.vue";
import { authRoutes } from "@/features/auth/router";
import { classifyRoutes } from "@/features/classify/router";
import { dashboardRoutes } from "@/features/dashboard/router";
import { datasetRoutes } from "@/features/datasets/router";
import { predictionRoutes } from "@/features/prediction/router";
import { previewRoutes } from "@/features/preview/router";
import { scheduleRoutes } from "@/features/schedules/router";
import { sensorRoutes } from "@/features/sensors/router";
import { taskTrackerRoutes } from "@/features/task_tracker/router";
import { trainingRoutes } from "@/features/training/router";

const AUTH_ROUTES = ["/login", "/register", "/auth/oauth/success", "/auth/oauth/register"];

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/preview" },
    ...authRoutes,
    ...dashboardRoutes,
    ...taskTrackerRoutes,
    ...datasetRoutes,
    ...classifyRoutes,
    ...trainingRoutes,
    ...predictionRoutes,
    ...scheduleRoutes,
    ...sensorRoutes,
    ...previewRoutes,
    {
      path: "/admin",
      component: AdminLayout,
      children: [
        { path: "", redirect: "/admin/dashboard" },
        { path: "dashboard", component: () => import("@/features/dashboard/presentation/pages/DashboardView.vue") },
      ],
    },
    {
      path: "/settings",
      component: SettingsLayout,
      children: [
        { path: "", redirect: "/settings/access-keys" },
        { path: "access-keys", component: () => import("@/features/settings/presentation/pages/SettingsView.vue") },
      ],
    },
    ...(import.meta.env.DEV ? sandboxRoutes : []),
    { path: "/:pathMatch(.*)*", name: "not-found", redirect: "/preview" },
  ],
});

router.beforeEach((to) => {
  const authStore = useAuthStore();
  const token = getStoredToken();
  const isAuthRoute = AUTH_ROUTES.includes(to.path);

  if (to.path.startsWith("/admin") && !authStore.user?.is_superadmin) {
    return "/datasets";
  }

  if (!authStore.authEnabled) {
    if (isAuthRoute) {
      return "/datasets";
    }
    return true;
  }

  if (isAuthRoute && token) {
    return "/datasets";
  }

  if (!isAuthRoute && !token) {
    return "/login";
  }

  return true;
});
