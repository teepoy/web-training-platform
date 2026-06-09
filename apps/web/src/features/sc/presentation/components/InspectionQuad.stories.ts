import type { Meta, StoryObj } from "@storybook/vue3";
import InspectionQuad from "./InspectionQuad.vue";
import type { ScSampleItem } from "@/features/sc/generated/proto/sc/v1/sample_pb";
import type { InspectionSummaryItem } from "@/features/sc/domain/models";

const INSPECTION_TIME = 1736939400;
const WAFER_RADIUS_NM = 150_000_000;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

function makeSamples(count: number): ScSampleItem[] {
  return Array.from({ length: count }, (_, i) => {
    const ratio = (i + 0.5) / count;
    const r = Math.sqrt(ratio) * WAFER_RADIUS_NM * 0.98;
    const theta = i * GOLDEN_ANGLE;
    return {
      defectId: i + 1,
      waferX: Math.round(r * Math.cos(theta)),
      waferY: Math.round(r * Math.sin(theta)),
      roughBin: (Math.abs(i) % 5) + 1,
      classNumber: i % 2 === 0 ? (i % 3) + 1 : undefined,
      inspectionTime: BigInt(INSPECTION_TIME),
      waferKey: 1,
      reviewImages: [],
    };
  });
}

function makeWaferDisplay(count: number): number[] {
  const arr: number[] = new Array(count * 6);
  for (let i = 0; i < count; i++) {
    const ratio = (i + 0.5) / count;
    const r = Math.sqrt(ratio) * WAFER_RADIUS_NM * 0.98;
    const theta = i * GOLDEN_ANGLE;
    arr[i * 6] = Math.round(r * Math.cos(theta));
    arr[i * 6 + 1] = Math.round(r * Math.sin(theta));
    arr[i * 6 + 2] = i + 1;
    arr[i * 6 + 3] = i % 2 === 0 ? (i % 3) + 1 : 0;
    arr[i * 6 + 4] = (Math.abs(i) % 5) + 1;
    arr[i * 6 + 5] = 0;
  }
  return arr;
}

function makeDieDisplay(count: number): number[] {
  const arr: number[] = new Array(count * 6);
  for (let i = 0; i < count; i++) {
    const ratio = (i + 0.5) / count;
    const r = Math.sqrt(ratio) * WAFER_RADIUS_NM * 0.98;
    const theta = i * GOLDEN_ANGLE;
    const wx = Math.round(r * Math.cos(theta));
    const wy = Math.round(r * Math.sin(theta));
    arr[i * 6] = ((wx % 8_000_000) + 8_000_000) % 8_000_000;
    arr[i * 6 + 1] = ((wy % 5_000_000) + 5_000_000) % 5_000_000;
    arr[i * 6 + 2] = i + 1;
    arr[i * 6 + 3] = i % 2 === 0 ? (i % 3) + 1 : 0;
    arr[i * 6 + 4] = (Math.abs(i) % 5) + 1;
    arr[i * 6 + 5] = 0;
  }
  return arr;
}

function makeReticleDisplay(count: number): number[] {
  const arr: number[] = new Array(count * 6);
  for (let i = 0; i < count; i++) {
    arr[i * 6] = (i * 37) % (10 * 8_000_000);
    arr[i * 6 + 1] = (i * 53) % (10 * 5_000_000);
    arr[i * 6 + 2] = i + 1;
    arr[i * 6 + 3] = i % 2 === 0 ? (i % 3) + 1 : 0;
    arr[i * 6 + 4] = (Math.abs(i) % 5) + 1;
    arr[i * 6 + 5] = 0;
  }
  return arr;
}

const inspectionItem: InspectionSummaryItem = {
  inspection_time: "2025-01-15T10:30:00",
  wafer_key: 1,
  lot_id: "",
  wafer_id: "",
  center_x: 150_000_000, center_y: 150_000_000,
  origin_x: 145_000_000, origin_y: 145_000_000,
  die_size_x: 8_000_000, die_size_y: 5_000_000,
  layer_id: "L1", eqp_id: "EQP-A", recipe_id: "REC-1",
  defects: 0, images: 0,
  device: "",
};

const meta = {
  component: InspectionQuad,
  title: "SC/components/InspectionQuad",
  tags: ["autodocs"],
  decorators: [
    () => ({
      template: '<div style="height:700px;display:flex;flex-direction:column;background:#0f0f1a"><story /></div>',
    }),
  ],
} satisfies Meta<typeof InspectionQuad>;

export default meta;
type Story = StoryObj<typeof meta>;

const N = 100;
export const Default: Story = {
  args: {
    samples: makeSamples(N),
    samplesTotal: N,
    samplesLoading: false,
    samplesError: null,
    inspectionItem,
    activeMapTab: "wafer",
    waferDisplay: makeWaferDisplay(N),
    dieDisplay: makeDieDisplay(N),
    reticleDisplay: makeReticleDisplay(N),
    reticleXDieCount: 10,
    reticleYDieCount: 10,
    reticleDieSizeX: inspectionItem.die_size_x,
    reticleDieSizeY: inspectionItem.die_size_y,
  },
};

export const Loading: Story = {
  args: {
    samples: [],
    samplesTotal: 0,
    samplesLoading: true,
    samplesError: null,
    inspectionItem,
    activeMapTab: "wafer",
  },
};

export const Error: Story = {
  args: {
    samples: [],
    samplesTotal: 0,
    samplesLoading: false,
    samplesError: "Failed to load inspection samples",
    inspectionItem,
    activeMapTab: "wafer",
  },
};

export const DieTabActive: Story = {
  args: {
    samples: makeSamples(80),
    samplesTotal: 80,
    samplesLoading: false,
    samplesError: null,
    inspectionItem,
    activeMapTab: "die",
    waferDisplay: makeWaferDisplay(80),
    dieDisplay: makeDieDisplay(80),
    reticleDisplay: makeReticleDisplay(80),
    reticleXDieCount: 10,
    reticleYDieCount: 10,
    reticleDieSizeX: inspectionItem.die_size_x,
    reticleDieSizeY: inspectionItem.die_size_y,
  },
  parameters: {
    docs: {
      description: {
        story:
          "Die Stack Map tab active. Click or brush-select points on the chart to filter the Sample Table and Blink Table below. Selected defect IDs will trigger a filtered view.",
      },
    },
  },
};

export const ReticleTabActive: Story = {
  args: {
    samples: makeSamples(80),
    samplesTotal: 80,
    samplesLoading: false,
    samplesError: null,
    inspectionItem,
    activeMapTab: "reticle",
    waferDisplay: makeWaferDisplay(80),
    dieDisplay: makeDieDisplay(80),
    reticleDisplay: makeReticleDisplay(80),
    reticleXDieCount: 10,
    reticleYDieCount: 10,
    reticleDieSizeX: inspectionItem.die_size_x,
    reticleDieSizeY: inspectionItem.die_size_y,
  },
};
