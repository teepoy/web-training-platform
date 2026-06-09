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

const Stub = defineComponent({ template: "<div />" });

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

  it("resolves effectiveDieFullPoints to dieDisplay when fullDieDisplay is empty []", () => {
    const stride6Data = MIXED_CLASS_POINTS;
    const wrapper = mount(InspectionQuad, {
      props: {
        samples: [],
        samplesTotal: stride6Data.length / 6,
        samplesLoading: false,
        samplesError: null,
        activeMapTab: "die",
        dieDisplay: stride6Data,
        fullDieDisplay: [],
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

  it("forwards full-die array when fullDieDisplay has data", () => {
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
        fullDieDisplay: fullData,
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

  it("passes undefined when both fullDieDisplay and dieDisplay are undefined", () => {
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
});
