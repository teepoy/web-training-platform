import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import { defineComponent } from "vue";

// Stub components
const ScMapPanel = defineComponent({
  name: "ScMapPanel",
  props: {
    activeMapTab: String,
    waferPoints: Array,
    waferFullPoints: Array,
    diePoints: Array,
    dieFullPoints: Array,
    reticlePoints: Array,
    reticleFullPoints: Array,
  },
  template: "<div />",
});

const Stub = defineComponent({
  name: "ScSampleTable",
  props: {
    filter: Object,
    sort: Object,
    selectedDefectIds: Object,
  },
  emits: ["filter-change", "sort-change", "selection-change", "apply-selection"],
  template: "<div />",
});

import InspectionQuad from "@/features/sc/presentation/components/InspectionQuad.vue";
import { MIXED_CLASS_POINTS } from "./scMapFixtures";

describe("InspectionQuad", () => {
  it("renders without error", () => {
    const wrapper = mount(InspectionQuad, {
      props: {
        samples: [],
        samplesTotal: 0,
        samplesLoading: false,
        samplesError: null,
        activeMapTab: "wafer",
      },
      global: {
        stubs: {
          ScMapPanel,
          ScSampleTable: Stub,
          ScPreviewBlinkVirtualTable: Stub,
        },
      },
    });
    expect(wrapper.exists()).toBe(true);
  });

  it("resolves effectiveDiePoints to dieDisplay when unzoomedDieDisplay is empty []", () => {
    const stride6Data = MIXED_CLASS_POINTS;
    const wrapper = mount(InspectionQuad, {
      props: {
        samples: [],
        samplesTotal: stride6Data.length / 6,
        samplesLoading: false,
        samplesError: null,
        activeMapTab: "die",
        dieDisplay: stride6Data,
        unzoomedDieDisplay: [],
      },
      global: {
        stubs: {
          ScMapPanel,
          ScSampleTable: Stub,
          ScPreviewBlinkVirtualTable: Stub,
        },
      },
    });

    const mapPanel = wrapper.findComponent({ name: "ScMapPanel" });
    expect(mapPanel.exists()).toBe(true);
    expect(mapPanel.props("dieFullPoints")).toEqual(stride6Data);
    expect(mapPanel.props("dieFullPoints")).not.toEqual([]);
  });

  it("forwards unzoomed-die array when unzoomedDieDisplay has data", () => {
    const stride6Data = MIXED_CLASS_POINTS;
    const fullData = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
    const wrapper = mount(InspectionQuad, {
      props: {
        samples: [],
        samplesTotal: stride6Data.length / 6,
        samplesLoading: false,
        samplesError: null,
        activeMapTab: "die",
        dieDisplay: stride6Data,
        unzoomedDieDisplay: fullData,
      },
      global: {
        stubs: {
          ScMapPanel,
          ScSampleTable: Stub,
          ScPreviewBlinkVirtualTable: Stub,
        },
      },
    });

    const mapPanel = wrapper.findComponent({ name: "ScMapPanel" });
    expect(mapPanel.exists()).toBe(true);
    expect(mapPanel.props("dieFullPoints")).toEqual(fullData);
  });

  it("passes undefined when both unzoomedDieDisplay and dieDisplay are undefined", () => {
    const wrapper = mount(InspectionQuad, {
      props: {
        samples: [],
        samplesTotal: 0,
        samplesLoading: false,
        samplesError: null,
        activeMapTab: "die",
      },
      global: {
        stubs: {
          ScMapPanel,
          ScSampleTable: Stub,
          ScPreviewBlinkVirtualTable: Stub,
        },
      },
    });

    const mapPanel = wrapper.findComponent({ name: "ScMapPanel" });
    expect(mapPanel.exists()).toBe(true);
    expect(mapPanel.props("dieFullPoints")).toBeUndefined();
  });

  it("forwards controlled table state and table events", async () => {
    const wrapper = mount(InspectionQuad, {
      props: {
        samples: [],
        samplesTotal: 3,
        samplesLoading: false,
        samplesError: null,
        activeMapTab: "wafer",
        tableFilter: {
          rough_bin: { filterType: "set", values: [1, 2] },
        },
        tableSort: { field: "defect_id", direction: "desc" },
        selectedDefectIds: [2],
      },
      global: {
        stubs: {
          ScMapPanel,
          ScSampleTable: Stub,
          ScPreviewBlinkVirtualTable: defineComponent({ template: "<div />" }),
        },
      },
    });
    const table = wrapper.findComponent({ name: "ScSampleTable" });

    expect(table.props("filter")).toEqual({
      rough_bin: { filterType: "set", values: [1, 2] },
    });
    expect(table.props("sort")).toEqual({
      field: "defect_id",
      direction: "desc",
    });

    table.vm.$emit("selection-change", [1, 2]);
    table.vm.$emit("apply-selection", [2, 3]);
    table.vm.$emit("filter-change", {
      rough_bin: { filterType: "set", values: [2, 3] },
    });
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("table-selection-change")?.[0]).toEqual([[1, 2]]);
    expect(wrapper.emitted("table-apply-selection")?.[0]).toEqual([[2, 3]]);
    expect(wrapper.emitted("table-filter-change")?.[0]).toEqual([
      { rough_bin: { filterType: "set", values: [2, 3] } },
    ]);
  });
});
