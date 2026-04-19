import { createApp } from "vue";
import { createPinia } from "pinia";
import { VueQueryPlugin, QueryClient } from "@tanstack/vue-query";

import "./style.css";
import App from "./App.vue";
import { router } from "./router";
import { useAuthStore } from "./stores/auth";

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
