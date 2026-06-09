import type { Component, ComponentPublicInstance } from "vue";
import type { Pinia } from "pinia";
import type { Router, RouteRecordRaw } from "vue-router";
import type { QueryClient } from "@tanstack/vue-query";
import type { VueWrapper } from "@vue/test-utils";
import { defineComponent } from "vue";
import { mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import naiveUI from "naive-ui";
import { VueQueryPlugin } from "@tanstack/vue-query";
import { createTestQueryClient } from "./query-client";

// ast-grep-ignore: disable-reexport
export { createTestQueryClient };

const defaultRouteComponent = defineComponent({ template: "<div />" });

export interface MountOptions {
  props?: Record<string, unknown>;
  slots?: Record<string, any>;
  global?: {
    stubs?: Record<string, any>;
    plugins?: any[];
    [key: string]: any;
  };
  routes?: RouteRecordRaw[];
  initialRoute?: string;
  queryClient?: QueryClient;
  pinia?: Pinia;
}

export interface MountResult {
  wrapper: VueWrapper<ComponentPublicInstance>;
  queryClient: QueryClient;
  router: Router;
  pinia: Pinia;
}

export async function mountWithProviders(
  component: Component,
  options: MountOptions = {},
): Promise<MountResult> {
  const {
    props,
    slots,
    global: userGlobal,
    routes,
    initialRoute,
    queryClient: userQueryClient,
    pinia: userPinia,
  } = options;

  const pinia = userPinia ?? createPinia();
  const queryClient = userQueryClient ?? createTestQueryClient();

  const router = createRouter({
    history: createMemoryHistory(),
    routes:
      routes && routes.length > 0
        ? routes
        : [
            {
              path: "/:pathMatch(.*)*",
              component: defaultRouteComponent,
            },
          ],
  });

  await router.push(initialRoute ?? "/");

  const builtinPlugins: any[] = [
    pinia,
    router,
    naiveUI,
    [VueQueryPlugin, { queryClient }],
  ];

  const wrapper: VueWrapper<ComponentPublicInstance> = mount(component, {
    props,
    slots,
    global: {
      plugins: [
        ...builtinPlugins,
        ...(userGlobal?.plugins ?? []),
      ],
      stubs: userGlobal?.stubs,
      ...Object.fromEntries(
        Object.entries(userGlobal ?? {}).filter(
          ([key]) => key !== "plugins" && key !== "stubs",
        ),
      ),
    },
    attachTo: document.body,
  });

  return { wrapper, queryClient, router, pinia };
}
