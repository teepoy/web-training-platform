import { describe, expect, it } from "vitest";
import { mountWithProviders } from "@/testing";
import ResourceFilterBar from "./ResourceFilterBar.vue";

describe("ResourceFilterBar", () => {
  it("shares search, creator, clear, and action presentation", async () => {
    const { wrapper } = await mountWithProviders(ResourceFilterBar, {
      props: {
        keyword: "inspection",
        keywordPlaceholder: "Search datasets",
        creatorScope: "all",
        creators: [{ id: "user-1", name: "Operator" }],
        activeFilterCount: 2,
        searchTestId: "resource-search",
      },
      slots: {
        actions: '<button data-testid="new-resource">New</button>',
      },
    });

    expect(
      (wrapper.get('[data-testid="resource-search"] input').element as HTMLInputElement).value,
    ).toBe("inspection");
    expect(wrapper.get('[data-testid="new-resource"]').text()).toBe("New");

    await wrapper.get("button.n-button").trigger("click");
    expect(wrapper.emitted("clear")).toHaveLength(1);
  });
});
