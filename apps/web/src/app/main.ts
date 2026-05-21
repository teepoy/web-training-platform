import { createApp } from "vue";
import { createPinia } from "pinia";
import { VueQueryPlugin, QueryClient } from "@tanstack/vue-query";
import { configureTransport } from "@/shared/api/client";

import "../style.css";
import "./registrations";
import App from "./App.vue";
import { router } from "./router";
import { useAuthStore, getStoredToken } from '@/features/auth/application/store';
import { useOrgStore } from '@/features/auth/application/org';

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
  authEnabled: () => {
    try {
      return useAuthStore(pinia).authEnabled;
    } catch {
      return true;
    }
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
  app.use(pinia);
  const authStore = useAuthStore(pinia);
  authStore.hydrateFromStorage();
  await authStore.initAuthMode();
  app.use(router);
  app.use(VueQueryPlugin, { queryClient });
  app.mount("#app");
}

void bootstrap();
