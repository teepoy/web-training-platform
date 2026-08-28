import { defineComponent, ref } from "vue";
import { flushPromises } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { mountWithProviders } from "@/testing";
import { useCreatorScopeQuery } from "./useCreatorScopeQuery";

const Harness = defineComponent({
  setup() {
    const orgId = ref("org-1");
    const userId = ref("user-1");
    const { creatorScope, creatorId, isReady } = useCreatorScopeQuery(orgId, userId);
    return { creatorScope, creatorId, isReady };
  },
  template: `
    <div>
      <span data-testid="scope">{{ creatorScope }}</span>
      <span data-testid="creator-id">{{ creatorId }}</span>
      <span data-testid="ready">{{ isReady }}</span>
      <button data-testid="all" @click="creatorScope = 'all'">All</button>
      <button data-testid="me" @click="creatorScope = 'me'">Mine</button>
    </div>
  `,
});

describe("useCreatorScopeQuery", () => {
  it("round-trips the default mine and explicit all scopes through the URL", async () => {
    const { wrapper, router } = await mountWithProviders(Harness, {
      initialRoute: "/models",
    });

    expect(wrapper.get('[data-testid="scope"]').text()).toBe("me");
    expect(wrapper.get('[data-testid="creator-id"]').text()).toBe("user-1");
    expect(wrapper.get('[data-testid="ready"]').text()).toBe("true");

    await wrapper.get('[data-testid="all"]').trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.creator).toBe("all");
    expect(wrapper.get('[data-testid="creator-id"]').text()).toBe("");

    await wrapper.get('[data-testid="me"]').trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.creator).toBeUndefined();
    expect(wrapper.get('[data-testid="creator-id"]').text()).toBe("user-1");
  });

  it("preserves a specific creator from the URL", async () => {
    const { wrapper } = await mountWithProviders(Harness, {
      initialRoute: "/models?creator=user-2",
    });

    expect(wrapper.get('[data-testid="scope"]').text()).toBe("user-2");
    expect(wrapper.get('[data-testid="creator-id"]').text()).toBe("user-2");
  });
});
