# Testing Utilities

## `mountWithProviders(component, options?)`

Mount a Vue component with all platform providers pre-installed:

- **Pinia** — fresh `createPinia()` (or provide your own)
- **Vue Router** — `createMemoryHistory()` with default catch-all route
- **Naive UI** — full plugin via `create({})` (Naive components need real DOM)
- **Vue Query** — fresh `QueryClient` from `createTestQueryClient()` (retry disabled)

Returns `{ wrapper, queryClient, router, pinia }` so tests can inspect state.

### Basic Usage

Mount a component and assert its rendered output:

```ts
import { mountWithProviders } from "@/testing";
import { describe, it, expect } from "vitest";
import MyWidget from "./MyWidget.vue";

describe("MyWidget", () => {
  it("renders the widget title", () => {
    const { wrapper } = mountWithProviders(MyWidget, {
      props: { title: "Hello" },
    });

    expect(wrapper.text()).toContain("Hello");
  });
});
```

### With Route

Mount a component that depends on `useRoute()` or `<RouterView>`:

```ts
import { mountWithProviders } from "@/testing";
import { describe, it, expect } from "vitest";
import DatasetDetailPage from "./DatasetDetailPage.vue";

describe("DatasetDetailPage", () => {
  it("reads datasetId from route params", () => {
    const { wrapper, router } = mountWithProviders(DatasetDetailPage, {
      routes: [
        { path: "/datasets/:id", component: DatasetDetailPage },
      ],
      initialRoute: "/datasets/abc-123",
    });

    expect(wrapper.text()).toContain("abc-123");
    expect(router.currentRoute.value.params.id).toBe("abc-123");
  });
});
```

### With State Override

Provide a pre-seeded Pinia store or custom QueryClient:

```ts
import { mountWithProviders, createTestQueryClient } from "@/testing";
import { createPinia, setActivePinia } from "pinia";
import { describe, it, expect } from "vitest";
import JobList from "./JobList.vue";
import { useJobStore } from "@/stores/jobs";

describe("JobList", () => {
  it("renders pre-loaded jobs from store", () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = useJobStore();
    store.jobs = [{ id: "j1", name: "Train V1" }];

    const queryClient = createTestQueryClient();
    queryClient.setQueryData(["jobs"], [{ id: "j1", name: "Train V1" }]);

    const { wrapper } = mountWithProviders(JobList, {
      pinia,
      queryClient,
    });

    expect(wrapper.text()).toContain("Train V1");
  });
});
```
