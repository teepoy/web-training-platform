import { createApp } from "vue";
import { createPinia } from "pinia";
import { VueQueryPlugin, QueryClient } from "@tanstack/vue-query";
import { configureTransport } from "@/shared/api/client";

import "../style.css";
import "vxe-pc-ui/lib/style.css";
import "vxe-table/lib/style.css";
import VxeUITable from "vxe-table";
import VxeUI from "vxe-pc-ui";
import "./registrations";
import App from "./App.vue";
import { router } from "./router";
import { useAuthStore, getStoredToken } from "@/features/auth/application/store";
import { useOrgStore } from "@/features/auth/application/org";
import { i18n, initializeAppLocale } from "./i18n";

configureTransport({
  getToken: () => {
    try {
      const auth = useAuthStore(pinia);
      return auth.token ?? getStoredToken();
    } catch {
      return getStoredToken();
    }
  },
  getOrgId: () => {
    try {
      return useOrgStore(pinia).currentOrgId;
    } catch {
      return null;
    }
  },
  onAuthError: () => {
    try {
      const auth = useAuthStore(pinia);
      auth.logout();
    } catch {}
    try {
      router.push("/login");
    } catch {}
  },
});

const app = createApp(App);
const pinia = createPinia();
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
    mutations: {
      retry: 0,
    },
  },
});

async function bootstrap(): Promise<void> {
  initializeAppLocale();
  app.use(pinia);
  const authStore = useAuthStore(pinia);
  authStore.hydrateFromStorage();
  app.use(router);
  app.use(VxeUI);
  app.use(VxeUITable);
  app.use(i18n);
  app.use(VueQueryPlugin, { queryClient });
  app.mount("#app");
}

void bootstrap();
