import { NButton, NModal } from "naive-ui";
import { describe, expect, it } from "vitest";
import { mountWithProviders } from "@/testing";
import ScBlinkVirtualTable from "./ScBlinkVirtualTable.vue";

describe("ScBlinkVirtualTable gallery settings", () => {
  it("separates layout and gray color mapping into tabs", async () => {
    const { wrapper } = await mountWithProviders(ScBlinkVirtualTable, {
      props: {
        inspectionTime: "2026-08-21T00:00:00Z",
        waferKey: 1,
      },
    });
    const settingsButton = wrapper
      .findAllComponents(NButton)
      .find((candidate) => candidate.text() === "Settings");
    if (!settingsButton) throw new Error("Gallery Settings button was not rendered");

    await settingsButton.trigger("click");

    expect(wrapper.findComponent(NModal).props("title")).toBe("Gallery Settings");
    const layoutTab = document.querySelector<HTMLElement>('[data-name="layout"]');
    const colorTab = document.querySelector<HTMLElement>('[data-name="color"]');
    expect(layoutTab?.textContent).toContain("Layout");
    expect(colorTab?.textContent).toContain("Color");
    colorTab?.click();
    await wrapper.vm.$nextTick();
    expect(document.querySelector('[data-testid="gallery-gray-mapping-toggle"]')).not.toBeNull();
  });
});
