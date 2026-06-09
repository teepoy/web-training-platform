import { vi } from "vitest";
import { h } from "vue";

// vi.mock calls are hoisted by vitest to execute before any test code.
// Importing this module applies the mocks; call mockEcharts() as an explicit
// opt-in marker at the top of your spec file.
vi.mock("echarts/core", () => ({
  use: vi.fn(),
}));

vi.mock("echarts/charts", () => ({
  LineChart: vi.fn(),
  BarChart: vi.fn(),
}));

vi.mock("echarts/components", () => ({
  GridComponent: vi.fn(),
  LegendComponent: vi.fn(),
  TooltipComponent: vi.fn(),
}));

vi.mock("echarts/renderers", () => ({
  CanvasRenderer: vi.fn(),
  SVGRenderer: vi.fn(),
}));

vi.mock("echarts", () => ({
  getInstanceByDom: vi.fn(() => null),
}));

vi.mock("vue-echarts", () => ({
  default: {
    name: "VChart",
    props: ["option", "theme", "autoresize"],
    setup() {
      return () => h("div", { class: "mock-vchart" });
    },
  },
}));

/** Opt-in marker — call at top of spec to explicitly apply echarts mocks. */
export function mockEcharts(): void {
  // vi.mock calls above are hoisted by vitest; this function is a no-op
  // that signals intent to human readers and linters.
}
