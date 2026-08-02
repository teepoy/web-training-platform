import { describe, expect, it } from "vitest";
import { mountWithProviders } from "@/testing";
import ScGlobalFilterBar from "./ScGlobalFilterBar.vue";

describe("ScGlobalFilterBar", () => {
  it("renders set and range controls for every preview table field", async () => {
    const { wrapper } = await mountWithProviders(ScGlobalFilterBar, {
      props: {
        filter: {},
        distinctValues: {},
      },
    });

    const labels = wrapper.findAll("button").map((button) => button.text());
    expect(labels).toContain("Defect ID");
    expect(labels).toContain("Area");
    expect(labels).toContain("Class");
    expect(labels).toContain("Kill Ratio");
  });

  it("adds reclassify fields when the reclassify table exposes them", async () => {
    const { wrapper } = await mountWithProviders(ScGlobalFilterBar, {
      props: {
        filter: {},
        distinctValues: {},
        showReclassifyColumns: true,
      },
    });

    const labels = wrapper.findAll("button").map((button) => button.text());
    expect(labels).toContain("Annotation");
    expect(labels).toContain("Prediction");
    expect(labels).toContain("Confidence");
    expect(labels).toContain("Final Class");
  });

  it("shows readable missing-value options for derived label fields", async () => {
    const { wrapper } = await mountWithProviders(ScGlobalFilterBar, {
      props: {
        filter: {},
        distinctValues: { prediction_label: ["__no_prediction__", "Scratch"] },
        showReclassifyColumns: true,
      },
    });

    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Prediction")
      ?.trigger("click");
    const setMenu = wrapper.findComponent({ name: "ScSetFilterMenu" });
    expect(setMenu.props("options")).toEqual([
      { label: "No Prediction", value: "__no_prediction__" },
      { label: "Scratch", value: "Scratch" },
    ]);
  });

  it("shows concise active states for set and range filters", async () => {
    const { wrapper } = await mountWithProviders(ScGlobalFilterBar, {
      props: {
        filter: {
          rough_bin: { filterType: "set", values: [1, 2] },
          area: { filterType: "number", type: "inRange", filter: 10, filterTo: 20 },
        },
        distinctValues: {},
      },
    });

    const labels = wrapper.findAll("button").map((button) => button.text());
    expect(labels).toContain("Rough Bin2");
    expect(labels).toContain("AreaOn");
    expect(labels).toContain("Clear all");
  });

  it("requests and fills queried bounds when a numeric filter opens", async () => {
    const { wrapper } = await mountWithProviders(ScGlobalFilterBar, {
      props: {
        filter: {},
        distinctValues: {},
      },
    });

    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Area")
      ?.trigger("click");
    expect(wrapper.emitted("request-range")).toEqual([["area"]]);

    await wrapper.setProps({ numericRanges: { area: { min: 1.25, max: 98.5 } } });
    const rangeMenu = wrapper.findComponent({ name: "ScRangeFilterMenu" });
    expect(rangeMenu.props("min")).toBe(1.25);
    expect(rangeMenu.props("max")).toBe(98.5);
  });
});
