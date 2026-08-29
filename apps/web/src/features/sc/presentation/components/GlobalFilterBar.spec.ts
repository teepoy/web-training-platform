import { describe, expect, it } from "vitest";
import { NSelect } from "naive-ui";
import { mountWithProviders } from "@/testing";
import type { ScGlobalFilter } from "@/features/sc/domain/globalFilter";
import type { ScDataColumn } from "@/features/sc/domain/workbenchDataSource";
import GlobalFilterBar from "./GlobalFilterBar.vue";

const filterColumns: ScDataColumn[] = [
  ["defect_id", "Defect ID", "set", "default"],
  ["area", "Area", "range", "default"],
  ["class_number", "Class", "set", "default"],
  ["kill_ratio", "Kill Ratio", "range", "default"],
  ["rough_bin", "Rough Bin", "set", "default"],
  ["annotation_label", "Annotation", "set", "reclassify"],
  ["prediction_label", "Prediction", "set", "reclassify"],
  ["prediction_confidence", "Confidence", "range", "reclassify"],
  ["final_class", "Final Class", "set", "filter_only"],
].map(([name, title, filter, visibility], order) => ({
  name,
  arrowType: filter === "range" ? "Float64" : "Utf8",
  nullable: true,
  presentation: {
    title,
    width: 120,
    filter,
    visibility,
    format: "plain",
    order,
  },
})) as ScDataColumn[];

function globalFilter(items: ScGlobalFilter["items"] = []): ScGlobalFilter {
  return { combinator: "and", items };
}

describe("GlobalFilterBar", () => {
  it("starts an incomplete draft without changing the effective filter", async () => {
    const { wrapper } = await mountWithProviders(GlobalFilterBar, {
      props: { filter: globalFilter(), columns: filterColumns, distinctValues: {} },
    });

    await wrapper.get('[data-testid="query-combinator-or"]').trigger("click");
    await wrapper.get('[data-testid="query-add-group"]').trigger("click");
    await wrapper.get('[data-testid="query-add-condition"]').trigger("click");

    const select = wrapper.findComponent(NSelect);
    const options = select.props("options") as Array<{ label: string; value: string }>;
    expect(options.map((option) => option.label)).toEqual(
      expect.arrayContaining(["Defect ID", "Area", "Class", "Kill Ratio"]),
    );
    expect(wrapper.emitted("update:filter")).toBeUndefined();
  });

  it("drops incomplete editor drafts when the workbench scope changes", async () => {
    const { wrapper } = await mountWithProviders(GlobalFilterBar, {
      props: {
        filter: globalFilter(),
        columns: filterColumns,
        distinctValues: {},
        resetKey: "inspection:one",
      },
    });

    await wrapper.get('[data-testid="query-add-condition"]').trigger("click");
    expect(wrapper.findComponent(NSelect).exists()).toBe(true);

    await wrapper.setProps({ resetKey: "inspection:two" });

    expect(wrapper.findComponent(NSelect).exists()).toBe(false);
    expect(wrapper.emitted("update:filter")).toBeUndefined();
  });

  it("offers reclassify properties when enabled", async () => {
    const { wrapper } = await mountWithProviders(GlobalFilterBar, {
      props: {
        filter: globalFilter(),
        columns: filterColumns,
        distinctValues: {},
        showReclassifyColumns: true,
      },
    });

    await wrapper.get('[data-testid="query-add-condition"]').trigger("click");
    const options = wrapper.findComponent(NSelect).props("options") as Array<{
      label: string;
    }>;
    expect(options.map((option) => option.label)).toEqual(
      expect.arrayContaining(["Annotation", "Prediction", "Confidence", "Final Class"]),
    );
  });

  it("promotes a configured draft to one complete item", async () => {
    const { wrapper } = await mountWithProviders(GlobalFilterBar, {
      props: {
        filter: globalFilter(),
        columns: filterColumns,
        distinctValues: { rough_bin: [1, 2] },
      },
    });

    await wrapper.get('[data-testid="query-add-condition"]').trigger("click");
    wrapper.findComponent(NSelect).vm.$emit("update:value", "rough_bin");
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).not.toContain("Configure");
    expect(wrapper.find(".sc-filter-rule__editor").exists()).toBe(true);
    wrapper.findComponent({ name: "SetFilterMenu" }).vm.$emit("apply", [2]);

    const emitted = wrapper.emitted("update:filter")?.at(-1)?.[0] as ScGlobalFilter;
    expect(emitted.combinator).toBe("and");
    expect(emitted.items).toHaveLength(1);
    expect(emitted.items[0]).toMatchObject({
      field: "rough_bin",
      condition: { filterType: "set", values: [2] },
      source: { kind: "manual" },
    });
    expect(emitted.items[0]?.id).toBeTruthy();
  });

  it("renders repeated properties as separately removable items", async () => {
    const filter = globalFilter([
      {
        id: "first",
        field: "defect_id",
        condition: { filterType: "set", values: [103], exclude: true },
        source: { kind: "map-selection", action: "exclude-selected" },
      },
      {
        id: "second",
        field: "defect_id",
        condition: { filterType: "set", values: [274], exclude: true },
        source: { kind: "map-selection", action: "exclude-selected" },
      },
    ]);
    const { wrapper } = await mountWithProviders(GlobalFilterBar, {
      props: { filter, columns: filterColumns, distinctValues: {} },
    });

    expect(wrapper.findAll(".query-builder__rule")).toHaveLength(2);
    expect(wrapper.findAll(".query-builder__join")).toHaveLength(1);
    const firstRow = wrapper.findAll(".sc-filter-rule__summary")[0]!;
    expect(firstRow.find(".sc-filter-rule__property").text()).toBe("Defect ID");
    expect(firstRow.find(".sc-filter-rule__operator").text()).toBe("excludes");
    expect(firstRow.find(".sc-filter-rule__value").text()).toBe("103");
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Delete")
      ?.trigger("click");

    expect(wrapper.emitted("update:filter")?.at(-1)).toEqual([globalFilter([filter.items[1]!])]);
  });

  it("updates one excluded Defect ID item without overwriting its sibling", async () => {
    const filter = globalFilter([
      {
        id: "first",
        field: "defect_id",
        condition: { filterType: "set", values: [103, 274], exclude: true },
        source: { kind: "manual" },
      },
      {
        id: "second",
        field: "defect_id",
        condition: { filterType: "set", values: [936] },
        source: { kind: "manual" },
      },
    ]);
    const { wrapper } = await mountWithProviders(GlobalFilterBar, {
      props: { filter, columns: filterColumns, distinctValues: {} },
    });

    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Edit")
      ?.trigger("click");
    const menu = wrapper.findComponent({ name: "DefectIdFilterMenu" });
    expect(menu.props("exclude")).toBe(true);
    menu.vm.$emit("apply", [274, 500], true);

    expect(wrapper.emitted("update:filter")?.at(-1)).toEqual([
      globalFilter([
        {
          ...filter.items[0]!,
          condition: { filterType: "set", values: [274, 500], exclude: true },
        },
        filter.items[1]!,
      ]),
    ]);
  });

  it("requests numeric bounds by item identity", async () => {
    const filter = globalFilter([
      {
        id: "area-filter",
        field: "area",
        condition: { filterType: "number", type: "inRange", filter: 10, filterTo: 20 },
        source: { kind: "manual" },
      },
    ]);
    const { wrapper } = await mountWithProviders(GlobalFilterBar, {
      props: {
        filter,
        columns: filterColumns,
        distinctValues: {},
        numericRanges: { "area-filter": { min: 1.25, max: 98.5 } },
      },
    });

    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Edit")
      ?.trigger("click");

    expect(wrapper.emitted("request-range")).toEqual([[{ field: "area", itemId: "area-filter" }]]);
    const rangeMenu = wrapper.findComponent({ name: "RangeFilterMenu" });
    expect(rangeMenu.props("min")).toBe(10);
    expect(rangeMenu.props("max")).toBe(20);
  });

  it("reorders complete items without changing their IDs or predicates", async () => {
    const filter = globalFilter([
      {
        id: "first",
        field: "rough_bin",
        condition: { filterType: "set", values: [1] },
        source: { kind: "manual" },
      },
      {
        id: "second",
        field: "class_number",
        condition: { filterType: "set", values: [2] },
        source: { kind: "manual" },
      },
    ]);
    const { wrapper } = await mountWithProviders(GlobalFilterBar, {
      props: { filter, columns: filterColumns, distinctValues: {} },
    });
    const rows = wrapper.findAll("[data-query-builder-node-id]");

    await rows[0]!.trigger("dragstart");
    await rows[1]!.trigger("drop");

    expect(wrapper.emitted("update:filter")?.at(-1)).toEqual([
      globalFilter([filter.items[1]!, filter.items[0]!]),
    ]);
  });
});
