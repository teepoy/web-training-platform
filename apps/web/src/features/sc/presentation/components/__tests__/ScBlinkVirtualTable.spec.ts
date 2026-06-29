import { describe, it, expect, vi } from "vitest";
import { mountWithProviders } from "@/testing";
import ScBlinkVirtualTable from "../ScBlinkVirtualTable.vue";

describe("ScBlinkVirtualTable - loading", () => {
  it("shows loading status when loading is true", async () => {
    const { wrapper } = await mountWithProviders(ScBlinkVirtualTable, {
      props: { loading: true },
    });
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("Loading...");
  });

  it("hides loading status when loading is false", async () => {
    const { wrapper } = await mountWithProviders(ScBlinkVirtualTable, {
      props: { loading: false },
    });
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).not.toContain("Loading...");
  });
});
