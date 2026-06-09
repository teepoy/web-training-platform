import { defineComponent, createApp, type App } from "vue";
import { VueQueryPlugin, type QueryClient } from "@tanstack/vue-query";
import { createTestQueryClient } from "./query-client";

export interface QuerySetupResult<T> {
  result: T;
  queryClient: QueryClient;
  app: App;
  cleanup: () => void;
}

export function withQuerySetup<T>(
  composable: () => T,
  queryClient?: QueryClient,
): QuerySetupResult<T> {
  let result!: T;
  const qc = queryClient ?? createTestQueryClient();

  const TestComponent = defineComponent({
    setup() {
      result = composable();
    },
    template: "<div />",
  });

  const app = createApp(TestComponent);
  app.use(VueQueryPlugin, { queryClient: qc });
  const el = document.createElement("div");
  app.mount(el);

  return {
    result,
    queryClient: qc,
    app,
    cleanup() {
      app.unmount();
      el.remove();
    },
  };
}
