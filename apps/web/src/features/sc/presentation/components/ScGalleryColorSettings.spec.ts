import { NSelect, NSlider, NSwitch } from "naive-ui";
import { describe, expect, it } from "vitest";
import { mountWithProviders } from "@/testing";
import ScGalleryColorSettings from "./ScGalleryColorSettings.vue";

describe("ScGalleryColorSettings", () => {
  it("renders a color bar and native Gray8/Gray16 windows", async () => {
    const { wrapper } = await mountWithProviders(ScGalleryColorSettings, {
      props: {
        enabled: true,
        lut: "viridis",
        zMin: 0.125,
        zMax: 0.875,
      },
    });

    expect(wrapper.get('[data-testid="gallery-color-bar"]').attributes("style")).toContain(
      "linear-gradient",
    );
    expect(wrapper.text()).toContain("Gray8 32–223");
    expect(wrapper.text()).toContain("Gray16 8,192–57,343");
  });

  it("emits direct control changes and constrains the normalized window", async () => {
    const { wrapper } = await mountWithProviders(ScGalleryColorSettings, {
      props: {
        enabled: false,
        lut: "gray",
        zMin: 0.2,
        zMax: 0.8,
      },
    });

    wrapper.findComponent(NSwitch).vm.$emit("update:value", true);
    wrapper.findComponent(NSelect).vm.$emit("update:value", "inferno");
    const slider = wrapper.findComponent(NSlider);
    slider.vm.$emit("update:value", [0.1, 0.9]);
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("update:zMin")).toBeUndefined();
    expect(wrapper.emitted("update:zMax")).toBeUndefined();
    slider.vm.$emit("dragend");
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted("update:enabled")).toEqual([[true]]);
    expect(wrapper.emitted("update:lut")).toEqual([["inferno"]]);
    expect(wrapper.emitted("update:zMin")).toEqual([[0.1]]);
    expect(wrapper.emitted("update:zMax")).toEqual([[0.9]]);
  });
});
