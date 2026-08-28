import { defineComponent } from "vue";
import { createPinia, setActivePinia } from "pinia";
import { flushPromises } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "@/features/auth/application/store";
import { useOrgStore } from "@/features/auth/application/org";
import { mountWithProviders } from "@/testing";
import { server } from "@/testing/msw/server";
import LibraryWorkspaceView from "./LibraryWorkspaceView.vue";

const DatasetListStub = defineComponent({
  name: "DatasetListView",
  props: {
    embedded: Boolean,
    search: { type: String, default: "" },
    creatorId: { type: String, default: null },
  },
  template: '<section data-testid="dataset-list-stub">Dataset list</section>',
});

const CollectionListStub = defineComponent({
  name: "DatasetCollectionListView",
  props: {
    embedded: Boolean,
    search: { type: String, default: "" },
    creatorId: { type: String, default: null },
  },
  emits: ["open-create"],
  setup(_, { emit, expose }) {
    expose({ openCreate: () => emit("open-create") });
    return {};
  },
  template: '<section data-testid="collection-list-stub">Collection list</section>',
});

function preparePinia() {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore(pinia).user = {
    id: "user-1",
    email: "user@example.com",
    name: "Current User",
    is_superadmin: false,
    created_at: "2026-01-01T00:00:00Z",
  };
  useOrgStore(pinia).currentOrgId = "org-1";
  return pinia;
}

async function mountLibrary(initialRoute: string) {
  const pinia = preparePinia();
  const result = await mountWithProviders(LibraryWorkspaceView, {
    pinia,
    initialRoute,
    routes: [{ path: "/library", component: LibraryWorkspaceView }],
    global: {
      stubs: {
        DatasetListView: DatasetListStub,
        DatasetCollectionListView: CollectionListStub,
      },
    },
  });
  await flushPromises();
  return result;
}

describe("Library workspace", () => {
  beforeEach(() => {
    server.use(
      http.get("/api/v1/datasets/creators", () =>
        HttpResponse.json([
          {
            id: "user-1",
            email: "user@example.com",
            name: "Current User",
            is_superadmin: false,
            created_at: "2026-01-01T00:00:00Z",
          },
        ]),
      ),
      http.get("/api/v1/dataset-collections/creators", () =>
        HttpResponse.json([{ id: "user-2", name: "Collection Creator" }]),
      ),
    );
  });

  it("opens Datasets by default and resolves the current-user URL scope", async () => {
    const { wrapper } = await mountLibrary("/library?q=flowers&creator=me");

    expect(wrapper.get("h1").text()).toBe("Library");
    const datasets = wrapper.getComponent(DatasetListStub);
    expect(datasets.props()).toMatchObject({
      embedded: true,
      search: "flowers",
      creatorId: "user-1",
    });
    expect(wrapper.findComponent(CollectionListStub).exists()).toBe(false);
  });

  it("switches tabs without losing the shared URL query", async () => {
    const { wrapper, router } = await mountLibrary(
      "/library?tab=datasets&q=flowers&creator=user-2",
    );

    await wrapper.get('[data-testid="library-tab-collections"]').trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.query).toMatchObject({
      tab: "collections",
      q: "flowers",
      creator: "user-2",
    });
    expect(wrapper.getComponent(CollectionListStub).props()).toMatchObject({
      embedded: true,
      search: "flowers",
      creatorId: "user-2",
    });

    await wrapper.get('[data-testid="library-search"] input').setValue("review");
    await flushPromises();
    await vi.waitFor(() => expect(router.currentRoute.value.query.q).toBe("review"));
  });

  it("keeps the explicit all-creators scope when Collections is opened directly", async () => {
    const { wrapper } = await mountLibrary("/library?tab=collections&creator=all");

    expect(wrapper.findComponent(DatasetListStub).exists()).toBe(false);
    expect(wrapper.getComponent(CollectionListStub).props("creatorId")).toBeNull();
    expect(wrapper.get('[data-testid="library-new-collection"]').text()).toBe("New collection");
    expect(wrapper.getComponent({ name: "CreatorScopeSelect" }).props("creators")).toContainEqual({
      id: "user-2",
      name: "Collection Creator",
    });
  });

  it("opens collection creation from the shared filter toolbar", async () => {
    const { wrapper } = await mountLibrary("/library?tab=collections&creator=all");
    const collectionList = wrapper.getComponent(CollectionListStub);

    await wrapper.get('[data-testid="library-new-collection"]').trigger("click");

    expect(collectionList.emitted("open-create")).toHaveLength(1);
  });
});
