import { describe, expect, it } from "vitest";
import { NDropdown } from "naive-ui";
import { mountWithProviders } from "@/testing";
import ScMapPanelBinned from "../ScMapPanelBinned.vue";

describe("ScMapPanelBinned unified map", () => {
  it("keeps one native map element while switching modes", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanelBinned, {
      props: {
        activeMapTab: "wafer",
        arrowData: new ArrayBuffer(8),
        mapLegendColumn: "class_number",
      },
    });

    expect(wrapper.findAll('[data-testid="sc-unified-map"]')).toHaveLength(1);
    expect(wrapper.find('[data-testid="sc-map-settings"]').exists()).toBe(true);
    await wrapper.setProps({ activeMapTab: "die" });
    expect(wrapper.findAll('[data-testid="sc-unified-map"]')).toHaveLength(1);
  });

  it("forwards native zoom and box-selection events", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanelBinned);
    const map = wrapper.find('[data-testid="sc-unified-map"]');
    const zoom = { x: 1, y: 2, w: 3, h: 4 };
    map.element.dispatchEvent(new CustomEvent("zoom-in", { detail: zoom }));
    map.element.dispatchEvent(new CustomEvent("box-select", { detail: zoom }));
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted("zoom-in")?.at(-1)?.[0]).toEqual(zoom);
    expect(wrapper.emitted("box-select")?.at(-1)?.[0]).toEqual(zoom);
  });

  it("forwards lasso selection and always clears selection on the native clear event", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanelBinned);
    const map = wrapper.find('[data-testid="sc-unified-map"]');
    const selection = {
      points: [
        { x: 0, y: 0 },
        { x: 10, y: 0 },
        { x: 5, y: 10 },
      ],
      region: { x: 0, y: 0, w: 10, h: 10 },
    };

    map.element.dispatchEvent(new CustomEvent("lasso-select", { detail: selection }));
    map.element.dispatchEvent(new CustomEvent("clear-selection"));
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted("lasso-select")?.at(-1)?.[0]).toEqual(selection);
    expect(wrapper.emitted("clear-selection")).toEqual([[]]);
    expect(wrapper.emitted("zoom-in")).toBeUndefined();
  });

  it("groups map interactions into one compact dropdown", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanelBinned);
    const dropdown = wrapper.findComponent(NDropdown);
    const labels = (dropdown.props("options") as Array<{ label?: string }>).map(
      (option) => option.label,
    );

    expect(wrapper.find('[data-testid="sc-map-tools-button"]').exists()).toBe(true);
    expect(labels).toEqual([
      "Box selection (append)",
      "Lasso selection (append)",
      "Drag to zoom",
      "Pan map",
    ]);
    expect(wrapper.find('[data-testid="sc-map-zoom-in-button"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="sc-map-zoom-out-button"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="sc-map-reset-zoom-button"]').exists()).toBe(true);
  });

  it("offers one-step zoom in and zoom out controls", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanelBinned, {
      props: {
        waferRadiusNm: 100,
        waferGeometry: {
          centerX: 0,
          centerY: 0,
          originX: 0,
          originY: 0,
          dieSizeX: 10,
          dieSizeY: 10,
        },
      },
    });

    await wrapper.find('[data-testid="sc-map-zoom-in-button"]').trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("zoom-in")?.at(-1)?.[0]).toEqual({
      x: -50,
      y: -50,
      w: 100,
      h: 100,
    });

    await wrapper.setProps({ zoom: { x: -50, y: -50, w: 100, h: 100 } });
    await wrapper.find('[data-testid="sc-map-reset-zoom-button"]').trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("zoom-in")?.at(-1)?.[0]).toBeNull();

    await wrapper.find('[data-testid="sc-map-zoom-out-button"]').trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("zoom-in")?.at(-1)?.[0]).toBeNull();
  });

  it("assigns camel-case custom-element properties and switches dropdown interaction mode", async () => {
    const arrowData = [new ArrayBuffer(8), new ArrayBuffer(16)];
    const { wrapper } = await mountWithProviders(ScMapPanelBinned, {
      props: { arrowData, mapLegendColumn: "rough_bin" },
    });
    const map = wrapper.find('[data-testid="sc-unified-map"]');
    const element = map.element as HTMLElement & {
      arrowData: ArrayBuffer[];
      legendColumn: string;
      interactionMode: string;
      showImageMarkers: boolean;
      defectSize: number;
    };

    expect(element.arrowData).toHaveLength(2);
    expect(element.arrowData[0]).toBe(arrowData[0]);
    expect(element.arrowData[1]).toBe(arrowData[1]);
    expect(element.legendColumn).toBe("rough_bin");
    expect(element.showImageMarkers).toBe(true);
    expect(element.defectSize).toBe(2);
    expect(element.interactionMode).toBe("select");
    wrapper.findComponent(NDropdown).vm.$emit("select", "zoomin");
    await wrapper.vm.$nextTick();
    expect(element.interactionMode).toBe("zoomin");
    wrapper.findComponent(NDropdown).vm.$emit("select", "lasso");
    await wrapper.vm.$nextTick();
    expect(element.interactionMode).toBe("lasso");
  });

  it("keeps the current map visible while a pan redraw is pending", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanelBinned, {
      props: { mapLoading: true },
    });
    expect(wrapper.find(".map-loading-overlay").exists()).toBe(true);

    wrapper.findComponent(NDropdown).vm.$emit("select", "pan");
    await wrapper.vm.$nextTick();
    wrapper
      .find('[data-testid="sc-unified-map"]')
      .element.dispatchEvent(new CustomEvent("zoom-in", { detail: { x: 1, y: 2, w: 3, h: 4 } }));
    await wrapper.vm.$nextTick();

    expect(wrapper.find(".map-loading-overlay").exists()).toBe(false);
  });
});
