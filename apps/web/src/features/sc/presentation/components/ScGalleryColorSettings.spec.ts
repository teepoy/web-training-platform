import { NRadioGroup, NSelect, NSlider, NSwitch } from "naive-ui";
import { describe, expect, it } from "vitest";
import { mountWithProviders } from "@/testing";
import ScGalleryColorSettings from "./ScGalleryColorSettings.vue";

describe("ScGalleryColorSettings", () => {
  it("renders a color bar and the active native bit-depth window", async () => {
    const { wrapper } = await mountWithProviders(ScGalleryColorSettings, {
      props: {
        enabled: true,
        mode: "global",
        adaptiveScope: "defective-reference",
        lut: "viridis",
        zMin: 0.125,
        zMax: 0.875,
        bitDepth: 12,
      },
    });

    expect(wrapper.get('[data-testid="gallery-color-bar"]').attributes("style")).toContain(
      "linear-gradient",
    );
    expect(wrapper.text()).toContain("12-bit window");
    expect(wrapper.text()).toContain("512–3,583");
  });

  it.each([
    { bitDepth: 8 as const, nativeWindow: "32–223" },
    { bitDepth: 16 as const, nativeWindow: "8,192–57,343" },
  ])("renders the $bitDepth-bit Colorbar domain", async ({ bitDepth, nativeWindow }) => {
    const { wrapper } = await mountWithProviders(ScGalleryColorSettings, {
      props: {
        enabled: true,
        mode: "global",
        adaptiveScope: "defective-reference",
        lut: "viridis",
        zMin: 0.125,
        zMax: 0.875,
        bitDepth,
      },
    });

    expect(wrapper.text()).toContain(`${bitDepth}-bit window`);
    expect(wrapper.text()).toContain(nativeWindow);
  });

  it("emits direct control changes and constrains the normalized window", async () => {
    const { wrapper } = await mountWithProviders(ScGalleryColorSettings, {
      props: {
        enabled: false,
        mode: "global",
        adaptiveScope: "defective-reference",
        lut: "gray",
        zMin: 0.2,
        zMax: 0.8,
        bitDepth: 12,
      },
    });

    wrapper.findComponent(NSwitch).vm.$emit("update:value", true);
    wrapper.findComponent(NRadioGroup).vm.$emit("update:value", "adaptive");
    wrapper.findComponent(NSelect).vm.$emit("update:value", "inferno");
    const slider = wrapper.findComponent(NSlider);
    slider.vm.$emit("update:value", [0.1, 0.9]);
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("update:zMin")).toBeUndefined();
    expect(wrapper.emitted("update:zMax")).toBeUndefined();
    slider.vm.$emit("dragend");
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted("update:enabled")).toEqual([[true]]);
    expect(wrapper.emitted("update:mode")).toEqual([["adaptive"]]);
    expect(wrapper.emitted("update:lut")).toEqual([["inferno"]]);
    expect(wrapper.emitted("update:zMin")).toEqual([[0.1]]);
    expect(wrapper.emitted("update:zMax")).toEqual([[0.9]]);
  });

  it("uses a per-defect adaptive mode and disables the global window slider", async () => {
    const { wrapper } = await mountWithProviders(ScGalleryColorSettings, {
      props: {
        enabled: true,
        mode: "adaptive",
        adaptiveScope: "defective-reference",
        lut: "viridis",
        zMin: 0.125,
        zMax: 0.875,
        bitDepth: 12,
      },
    });

    expect(wrapper.findComponent(NSlider).props("disabled")).toBe(true);
    expect(wrapper.text()).toContain("Per defect; Defective and Reference share one range.");
  });

  it("describes Difference adaptive mapping as an independent image range", async () => {
    const { wrapper } = await mountWithProviders(ScGalleryColorSettings, {
      props: {
        enabled: true,
        mode: "adaptive",
        adaptiveScope: "image",
        lut: "viridis",
        zMin: 0.125,
        zMax: 0.875,
        bitDepth: 12,
      },
    });

    expect(wrapper.text()).toContain("Each Difference image uses its own range.");
  });
});
