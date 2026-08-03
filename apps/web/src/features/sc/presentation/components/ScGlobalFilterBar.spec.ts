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
});
