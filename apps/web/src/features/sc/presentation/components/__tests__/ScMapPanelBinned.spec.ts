import { describe, expect, it } from "vitest";
import { NDropdown } from "naive-ui";
import { mountWithProviders } from "@/testing";
import ScMapPanelBinned from "../ScMapPanelBinned.vue";
import ScLegend from "../ScLegend.vue";

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

  it("keeps native map error context visible", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanelBinned);
    wrapper.find('[data-testid="sc-unified-map"]').element.dispatchEvent(
      new CustomEvent("map-error", {
        detail: {
          context: "Loading Arrow map dataset",
          message: "ArrayBuffer at index 0 is already detached",
          stack: "Error: detached\n  at request (map-arrow-client.ts:1:1)",
        },
      }),
    );
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain(
      "Loading Arrow map dataset: ArrayBuffer at index 0 is already detached",
    );
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

  it("clears the local legend highlight when the transient selection is reset", async () => {
    const groups = {
      "2": { $typeName: "sc.v1.DefectList", count: 1, defectIds: [2] },
    };
    const { wrapper } = await mountWithProviders(ScMapPanelBinned, {
      props: { legendGroups: groups, selectionResetVersion: 0 },
    });
    const legend = wrapper.findComponent(ScLegend);

    legend.vm.$emit("select-class", 2);
    await wrapper.vm.$nextTick();
    expect(legend.props("selectedClassNumber")).toBe(2);

    await wrapper.setProps({ selectionResetVersion: 1 });
    expect(legend.props("selectedClassNumber")).toBeNull();
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

  it("lets the user include or exclude selected defects from the map context menu", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanelBinned, {
      props: { mapSelectionCount: 2 },
    });
    const map = wrapper.find('[data-testid="sc-unified-map"]');
    map.element.dispatchEvent(new CustomEvent("map-context-menu", { detail: { x: 120, y: 240 } }));
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    const menu = wrapper
      .findAllComponents(NDropdown)
      .find((dropdown) => dropdown.props("trigger") === "manual");

    expect(wrapper.find('[data-testid="sc-map-selection-mode"]').exists()).toBe(false);
    expect(menu).toBeDefined();
    if (!menu) throw new Error("map selection context menu was not mounted");
    expect(menu.props("show")).toBe(true);
    expect(menu.props("x")).toBe(120);
    expect(menu.props("y")).toBe(240);
    const options = menu.props("options") as Array<{
      label?: string;
      key?: string;
      disabled?: boolean;
      children?: Array<{ label?: string }>;
    }>;
    expect(options.slice(0, 4)).toEqual([
      { label: "Exclude all others", key: "include", disabled: false },
      { label: "Exclude selected", key: "exclude", disabled: false },
      { label: "Invert selection", key: "invert-selection", disabled: false },
      { label: "Copy selected defect IDs", key: "copy-selected-defect-ids", disabled: false },
    ]);
    expect(options[4]?.label).toBe("Selection tool");
    expect(options[4]?.children?.map((option) => option.label)).toEqual([
      "Box selection (append)",
      "Lasso selection (append)",
    ]);
    expect(options[5]?.label).toBe("Navigation tool");
    expect(options[5]?.children?.map((option) => option.label)).toEqual([
      "Drag to zoom",
      "Pan map",
    ]);

    menu.vm.$emit("select", "exclude");
    menu.vm.$emit("select", "invert-selection");
    menu.vm.$emit("select", "copy-selected-defect-ids");

    expect(wrapper.emitted("commit-map-selection-filter")?.at(-1)).toEqual(["exclude"]);
    expect(wrapper.emitted("invert-map-selection-mode")).toEqual([[]]);
    expect(wrapper.emitted("copy-selected-defect-ids")).toEqual([[]]);
  });

  it("closes the map context menu on a left pointer down", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanelBinned, {
      props: { mapSelectionCount: 2 },
    });
    const map = wrapper.find('[data-testid="sc-unified-map"]');
    map.element.dispatchEvent(new CustomEvent("map-context-menu", { detail: { x: 12, y: 24 } }));
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    const menu = wrapper
      .findAllComponents(NDropdown)
      .find((dropdown) => dropdown.props("trigger") === "manual");
    if (!menu) throw new Error("map selection context menu was not mounted");
    expect(menu.props("show")).toBe(true);

    map.element.dispatchEvent(new PointerEvent("pointerdown", { button: 0, bubbles: true }));
    await wrapper.vm.$nextTick();

    expect(menu.props("show")).toBe(false);
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

  it("keeps custom colors separate by legend source and restores them by scope", async () => {
    const groups = {
      "2": { $typeName: "sc.v1.DefectList", count: 5, defectIds: [1, 2] },
    };
    const { wrapper } = await mountWithProviders(ScMapPanelBinned, {
      props: {
        legendGroupBy: "class",
        legendGroups: groups,
        colorMapScopeKey: "dataset:colors",
      },
    });

    wrapper.findComponent(ScLegend).vm.$emit("update:colorMap", { "2": "#ff00ff" });
    await wrapper.vm.$nextTick();
    expect(
      (
        wrapper.find('[data-testid="sc-unified-map"]').element as HTMLElement & {
          colorMap: Record<string, string>;
        }
      ).colorMap,
    ).toEqual({ "2": "#ff00ff" });

    await wrapper.setProps({
      legendGroupBy: "prediction",
      legendGroups: {
        Scratch: { $typeName: "sc.v1.DefectList", count: 2, defectIds: [3, 4] },
      },
    });
    wrapper.findComponent(ScLegend).vm.$emit("update:colorMap", { Scratch: "#00ff00" });
    await wrapper.vm.$nextTick();

    await wrapper.setProps({ legendGroupBy: "class", legendGroups: groups });
    await wrapper.vm.$nextTick();
    expect(
      (
        wrapper.find('[data-testid="sc-unified-map"]').element as HTMLElement & {
          colorMap: Record<string, string>;
        }
      ).colorMap,
    ).toEqual({ "2": "#ff00ff" });
    expect(localStorage.getItem("sc_map_panel.color_map.dataset%3Acolors.class")).toBe(
      '{"2":"#ff00ff"}',
    );
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
