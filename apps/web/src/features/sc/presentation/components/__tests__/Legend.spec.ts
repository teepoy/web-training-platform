import { describe, it, expect } from "vitest";
import { mountWithProviders } from "@/testing";
import Legend from "../Legend.vue";
import { MIXED_CLASS_POINTS, EMPTY_POINTS } from "./scMapFixtures";

describe("Legend", () => {
  it("renders empty state when points are empty", async () => {
    const { wrapper } = await mountWithProviders(Legend, {
      props: {
        points: EMPTY_POINTS,
      },
    });

    expect(wrapper.find('[data-testid="sc-legend-empty"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("No classes");
  });

  it("renders legend items for mixed classes in ascending order", async () => {
    const { wrapper } = await mountWithProviders(Legend, {
      props: {
        points: MIXED_CLASS_POINTS,
      },
    });

    expect(wrapper.find('[data-testid="sc-legend-empty"]').exists()).toBe(false);

    expect(wrapper.find('[data-testid="sc-legend-class-0"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="sc-legend-class-1"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="sc-legend-class-2"]').exists()).toBe(true);

    const items = wrapper.findAll(".sc-legend-item");
    expect(items).toHaveLength(3);

    expect(items[0].text()).toContain("0");
    expect(items[0].text()).toContain("1");

    expect(items[1].text()).toContain("1");
    expect(items[1].text()).toContain("2");

    expect(items[2].text()).toContain("2");
    expect(items[2].text()).toContain("1");
  });

  it("emits hidden legend keys from the visible button", async () => {
    const { wrapper } = await mountWithProviders(Legend, {
      props: {
        points: MIXED_CLASS_POINTS,
      },
    });

    await wrapper.find('[data-testid="sc-legend-visible-1"]').trigger("click");

    expect(wrapper.emitted("update:hiddenKeys")?.[0]).toEqual([["1"]]);
  });

  it("clicking class 1 emits select-class with class number 1", async () => {
    const { wrapper } = await mountWithProviders(Legend, {
      props: {
        points: MIXED_CLASS_POINTS,
      },
    });

    await wrapper.find('[data-testid="sc-legend-class-1"]').trigger("click");

    const emits = wrapper.emitted("select-class");
    expect(emits).toBeTruthy();
    expect(emits![0][0]).toEqual(1);
  });

  it("clicking class 0 emits select-class with class number 0", async () => {
    const { wrapper } = await mountWithProviders(Legend, {
      props: {
        points: MIXED_CLASS_POINTS,
      },
    });

    await wrapper.find('[data-testid="sc-legend-class-0"]').trigger("click");

    const emits = wrapper.emitted("select-class");
    expect(emits).toBeTruthy();
    expect(emits![0][0]).toEqual(0);
  });

  it("clicking the already selected class emits select-class with null", async () => {
    const { wrapper } = await mountWithProviders(Legend, {
      props: {
        points: MIXED_CLASS_POINTS,
        selectedClassNumber: 1,
      },
    });

    await wrapper.find('[data-testid="sc-legend-class-1"]').trigger("click");

    const emits = wrapper.emitted("select-class");
    expect(emits).toBeTruthy();
    expect(emits![0][0]).toEqual(null);
  });

  it("renders and selects string annotation labels", async () => {
    const { wrapper } = await mountWithProviders(Legend, {
      props: {
        legendSource: "annotation",
        annotations: {
          Scratch: {
            $typeName: "sc.v1.DefectList",
            count: 2,
            defectIds: [101, 102],
          },
        },
      },
    });

    const item = wrapper.find('[data-testid="sc-legend-class-Scratch"]');
    expect(item.text()).toContain("Scratch");
    expect(item.text()).toContain("2");

    await item.trigger("click");
    expect(wrapper.emitted("select-class")?.[0]).toEqual(["Scratch"]);
  });

  it("hides the synthetic unlabeled group from Annotation", async () => {
    const { wrapper } = await mountWithProviders(Legend, {
      props: {
        legendSource: "annotation",
        annotations: {
          __unlabeled__: {
            $typeName: "sc.v1.DefectList",
            count: 3,
            defectIds: [2, 3, 4],
          },
        },
      },
    });

    expect(wrapper.text()).not.toContain("Unlabeled");
    expect(wrapper.text()).not.toContain("__unlabeled__");
  });

  it("emits color map updates from the color picker", async () => {
    const { wrapper } = await mountWithProviders(Legend, {
      props: {
        points: MIXED_CLASS_POINTS,
        colorMap: { "1": "#ff0000" },
      },
    });

    const input = wrapper.findAll<HTMLInputElement>(".sc-legend-color-input")[1];
    await input.setValue("#00ff00");

    expect(wrapper.emitted("update:colorMap")?.[0]).toEqual([{ "1": "#00ff00" }]);
  });

  it("uses the numeric annotation class as the color-map key", async () => {
    const { wrapper } = await mountWithProviders(Legend, {
      props: {
        legendSource: "annotation",
        annotations: {
          "7": {
            $typeName: "sc.v1.DefectList",
            count: 2,
            defectIds: [101, 102],
          },
        },
      },
    });

    await wrapper.find<HTMLInputElement>(".sc-legend-color-input").setValue("#00ff00");

    expect(wrapper.emitted("update:colorMap")?.[0]).toEqual([{ "7": "#00ff00" }]);
  });
});
