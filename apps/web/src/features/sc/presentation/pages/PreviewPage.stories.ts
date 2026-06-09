import type { Meta, StoryObj } from "@storybook/vue3";
import {
  createRouter,
  createMemoryHistory,
  routerKey,
  routeLocationKey,
} from "vue-router";
import { provide, onUnmounted } from "vue";
import { create, toBinary } from "@bufbuild/protobuf";
import {
  InspectionSampleResponseSchema,
  ScSampleItemSchema,
} from "../../generated/proto/sc/v1/sample_pb";
import type { InspectionSummaryPage } from "../../domain/models";
import PreviewPage from "./PreviewPage.vue";

const DATASET_ID = "mock-sc-dataset-1";
const INSPECTION_TIME_BIGINT = BigInt(Math.floor(new Date("2025-01-15T10:30:00").getTime() / 1000));

const MOCK_INSPECTIONS_JSON = JSON.stringify({
  items: [
    {
      inspection_time: "2025-01-15T10:30:00",
      wafer_key: 1,
      lot_id: "",
      wafer_id: "",
      center_x: 150_000_000,
      center_y: 150_000_000,
      origin_x: 145_000_000,
      origin_y: 145_000_000,
      die_size_x: 8_000_000,
      die_size_y: 5_000_000,
      device: "",
      layer_id: "L1",
      eqp_id: "EQP-A",
      recipe_id: "REC-1",
      defects: 12,
      images: 24,
    },
    {
      inspection_time: "2025-01-15T11:00:00",
      wafer_key: 2,
      lot_id: "",
      wafer_id: "",
      center_x: 0,
      center_y: 0,
      origin_x: 0,
      origin_y: 0,
      die_size_x: 6_000_000,
      die_size_y: 3_000_000,
      device: "",
      layer_id: "L2",
      eqp_id: "EQP-A",
      recipe_id: "REC-1",
      defects: 8,
      images: 16,
    },
    {
      inspection_time: "2025-01-15T11:30:00",
      wafer_key: 3,
      lot_id: "",
      wafer_id: "",
      center_x: 0,
      center_y: 0,
      origin_x: 0,
      origin_y: 0,
      die_size_x: 6_000_000,
      die_size_y: 3_000_000,
      device: "",
      layer_id: "L3",
      eqp_id: "EQP-B",
      recipe_id: "REC-2",
      defects: 5,
      images: 10,
    },
  ],
  total: 3,
} satisfies InspectionSummaryPage);

const MOCK_SAMPLE_COUNT = 100;
const WAFER_RADIUS_NM = 150_000_000;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

function mockSampleItems() {
  const items = new Array(MOCK_SAMPLE_COUNT);
  for (let i = 0; i < MOCK_SAMPLE_COUNT; i++) {
    const ratio = (i + 0.5) / MOCK_SAMPLE_COUNT;
    const r = Math.sqrt(ratio) * WAFER_RADIUS_NM * 0.98;
    const theta = i * GOLDEN_ANGLE;
    items[i] = {
      defectId: i + 1,
      waferX: Math.round(r * Math.cos(theta)),
      waferY: Math.round(r * Math.sin(theta)),
      roughBin: (Math.abs(i) % 5) + 1,
      classNumber: i % 2 === 0 ? (i % 3) + 1 : undefined,
      inspectionTime: INSPECTION_TIME_BIGINT,
      waferKey: 1,
      reviewImages: [],
    };
  }
  return items;
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

let _mockSamplesBinary: Uint8Array | null = null;

function getMockSamplesBinary(): Uint8Array {
  if (_mockSamplesBinary) return _mockSamplesBinary;
  const protoItems = mockSampleItems().map((i) => create(ScSampleItemSchema, i));
  _mockSamplesBinary = toBinary(
    InspectionSampleResponseSchema,
    create(InspectionSampleResponseSchema, {
      items: protoItems,
      total: MOCK_SAMPLE_COUNT,
      waferKey: 1,
      display: {
        waferXyId: makeWaferDisplay(MOCK_SAMPLE_COUNT),
        dieXyId: makeDieDisplay(MOCK_SAMPLE_COUNT),
      },
    }),
  );
  return _mockSamplesBinary;
}

const originalFetch = window.fetch.bind(window);

window.fetch = (async (input, init) => {
  const url =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.href
        : (input as Request)?.url || "";

  return originalFetch(input, init);
}) as typeof window.fetch;

const mockRouter = createRouter({
  history: createMemoryHistory(),
  routes: [
    {
      path: "/sc/preview",
      name: "sc-preview",
      component: PreviewPage,
    },
  ],
});

mockRouter.push({
  name: "sc-preview",
  query: { datasetId: DATASET_ID },
});

const meta = {
  component: PreviewPage,
  title: "SC/views/PreviewPage",
  parameters: {
    backgrounds: { default: "dark" },
    layout: "fullscreen",
  },
  decorators: [
    () => ({
      template: "<div style='height:100vh;overflow:hidden;display:flex;flex-direction:column'><story /></div>",
      setup() {
        onUnmounted(() => {
          window.fetch = originalFetch;
        });
        provide(routerKey, mockRouter);
        provide(routeLocationKey, mockRouter.currentRoute.value);
      },
    }),
  ],
} satisfies Meta<typeof PreviewPage>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
