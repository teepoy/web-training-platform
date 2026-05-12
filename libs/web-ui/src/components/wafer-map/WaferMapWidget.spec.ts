import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { defineComponent, h, shallowRef } from "vue";
import { DATA_PIPELINE_KEY } from "../../composables/useDataPipeline";

vi.mock("echarts/core", () => ({
  use: vi.fn(),
}));

vi.mock("echarts", () => ({
  getInstanceByDom: vi.fn(() => null),
}));

vi.mock("echarts/charts", () => ({
  LineChart: {},
  ScatterChart: {},
}));

vi.mock("echarts/components", () => ({
  GridComponent: {},
  TooltipComponent: {},
}));

vi.mock("echarts/renderers", () => ({
  CanvasRenderer: {},
}));

vi.mock("vue-echarts", () => ({
  default: defineComponent({
    name: "VChart",
    props: ["option", "theme", "autoresize"],
    setup() {
      return () => h("div", { class: "mock-vchart" });
    },
  }),
}));

vi.mock("kdbush", () => ({
  default: class MockKDBush {
    _points: Array<{ x: number; y: number }> = [];
    constructor(..._args: unknown[]) {}
    add(x: number, y: number) {
      this._points.push({ x, y });
    }
    finish() {}
    range(
      _minX: number,
      _minY: number,
      _maxX: number,
      _maxY: number,
    ): number[] {
      return [];
    }
  },
}));

import WaferMapWidget from "./WaferMapWidget.vue";

const mockRegister = vi.fn((id: string) => ({
  id,
  parentId: null,
  annotation: shallowRef(null),
  annotate: vi.fn(),
  clear: vi.fn(),
}));

const mockPipeline = {
  rawItems: shallowRef([]),
  register: mockRegister,
  getNode: vi.fn(),
  nodes: shallowRef({}),
};

const commonProvide = {
  [DATA_PIPELINE_KEY as symbol]: mockPipeline,
};

const DEFAULT_WAFER_RADIUS_NM = 150_000_000;

interface ChartSeriesItem {
  name?: string;
  type?: string;
  symbolSize?: number;
}

interface EChartsLikeOption {
  series?: ChartSeriesItem[];
  xAxis?: { min?: number; max?: number };
  yAxis?: { min?: number; max?: number };
}

function chartOption(wrapper: ReturnType<typeof mount>): EChartsLikeOption {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (wrapper.vm as any).chartOption as EChartsLikeOption;
}

function stableChartOption(
  wrapper: ReturnType<typeof mount>,
): EChartsLikeOption {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (wrapper.vm as any).stableChartOption as EChartsLikeOption;
}

describe("WaferMapWidget scatterSize", () => {
  it("defaults to 1 when no config provided", () => {
    const wrapper = mount(WaferMapWidget, { global: { provide: commonProvide },
      props: { data: null, config: undefined },
    });
    const wafer = chartOption(wrapper).series?.find(
      (s) => s.name === "wafer",
    );
    expect(wafer?.symbolSize).toBe(1);
  });

  it("clamps 0 to 0.1", () => {
    const wrapper = mount(WaferMapWidget, { global: { provide: commonProvide },
      props: { data: null, config: { scatterSize: 0 } },
    });
    const wafer = chartOption(wrapper).series?.find(
      (s) => s.name === "wafer",
    );
    expect(wafer?.symbolSize).toBe(0.1);
  });

  it("clamps -5 to 0.1", () => {
    const wrapper = mount(WaferMapWidget, { global: { provide: commonProvide },
      props: { data: null, config: { scatterSize: -5 } },
    });
    const wafer = chartOption(wrapper).series?.find(
      (s) => s.name === "wafer",
    );
    expect(wafer?.symbolSize).toBe(0.1);
  });

  it("clamps 50 to 20", () => {
    const wrapper = mount(WaferMapWidget, { global: { provide: commonProvide },
      props: { data: null, config: { scatterSize: 50 } },
    });
    const wafer = chartOption(wrapper).series?.find(
      (s) => s.name === "wafer",
    );
    expect(wafer?.symbolSize).toBe(20);
  });

  it("uses the provided value when in range", () => {
    const wrapper = mount(WaferMapWidget, { global: { provide: commonProvide },
      props: { data: null, config: { scatterSize: 5 } },
    });
    const wafer = chartOption(wrapper).series?.find(
      (s) => s.name === "wafer",
    );
    expect(wafer?.symbolSize).toBe(5);
  });
});

describe("WaferMapWidget die-grid", () => {
  it("is present in series when dieGrid config provided", () => {
    const wrapper = mount(WaferMapWidget, { global: { provide: commonProvide },
      props: {
        data: null,
        config: {
          dieGrid: {
            dieWidthNm: 10_000_000,
            dieHeightNm: 10_000_000,
            originX: 0,
            originY: 0,
          },
        },
      },
    });
    const dieGrid = chartOption(wrapper).series?.find(
      (s) => s.name === "die-grid",
    );
    expect(dieGrid).toBeDefined();
    expect(dieGrid?.name).toBe("die-grid");
    expect(dieGrid?.type).toBe("line");
  });

  it("is absent in series when dieGrid has zero dimensions", () => {
    const wrapper = mount(WaferMapWidget, { global: { provide: commonProvide },
      props: {
        data: null,
        config: {
          dieGrid: {
            dieWidthNm: 0,
            dieHeightNm: 0,
            originX: 0,
            originY: 0,
          },
        },
      },
    });
    const dieGrid = chartOption(wrapper).series?.find(
      (s) => s.name === "die-grid",
    );
    expect(dieGrid).toBeUndefined();
  });
});

describe("WaferMapWidget viewport decoupling", () => {
  it("chartOption equals stableChartOption by reference", () => {
    const wrapper = mount(WaferMapWidget, { global: { provide: commonProvide },
      props: { data: null, config: undefined },
    });
    const vm = wrapper.vm as Record<string, unknown>;
    expect(vm.chartOption).toBe(vm.stableChartOption);
  });
});

describe("WaferMapWidget stableChartOption defaults", () => {
  it("has default xAxis/yAxis boundaries set to ±DEFAULT_WAFER_RADIUS_NM", () => {
    const wrapper = mount(WaferMapWidget, { global: { provide: commonProvide },
      props: { data: null, config: undefined },
    });
    const option = stableChartOption(wrapper);

    expect(option.xAxis?.min).toBe(-DEFAULT_WAFER_RADIUS_NM);
    expect(option.xAxis?.max).toBe(DEFAULT_WAFER_RADIUS_NM);
    expect(option.yAxis?.min).toBe(-DEFAULT_WAFER_RADIUS_NM);
    expect(option.yAxis?.max).toBe(DEFAULT_WAFER_RADIUS_NM);
  });

  it("includes wafer-boundary and wafer series by default", () => {
    const wrapper = mount(WaferMapWidget, { global: { provide: commonProvide },
      props: { data: null, config: undefined },
    });
    const series = chartOption(wrapper).series;
    expect(series?.find((s) => s.name === "wafer-boundary")).toBeDefined();
    expect(series?.find((s) => s.name === "wafer")).toBeDefined();
  });
});
