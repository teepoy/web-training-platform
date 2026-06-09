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
import ReclassifyPage from "./ReclassifyPage.vue";

const DATASET_ID = "mock-sc-dataset-1";
const INSPECTION_TIME = "2025-01-15T10:30:00";
const WAFER_KEY = 1;

const MOCK_DATASET = {
  id: DATASET_ID,
  name: "Patch_LOT-2026-001_WAF-001_2026-05-26-08-00-00.000000",
  label_space: ["Normal", "Scratch", "Particle", "Crack", "Void"],
  task_spec: { task_type: "semiconductor" },
};

const MOCK_SAMPLE_COUNT = 30;

function _makeSamples(count: number) {
  const items = new Array(count);
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  const radius = 150_000_000;
  for (let i = 0; i < count; i++) {
    const ratio = (i + 0.5) / count;
    const r = Math.sqrt(ratio) * radius * 0.98;
    const theta = i * goldenAngle;
    items[i] = {
      sampleId: `s-${String(i + 1).padStart(3, "0")}`,
      defectId: `def-${String(i + 1).padStart(4, "0")}`,
      waferX: Math.round(r * Math.cos(theta)),
      waferY: Math.round(r * Math.sin(theta)),
      roughBin: (i % 5) + 1,
      classNumber: i % 3 === 0 ? undefined : (i % 4) + 1,
      reviewImages: [] as { imageName: string; imageId: number; imageType: string }[],
      inspectionTime: INSPECTION_TIME,
      waferKey: WAFER_KEY,
    };
  }
  return items;
}

let _mockSamplesBinary: Uint8Array | null = null;

function getMockSamplesBinary(): Uint8Array {
  if (_mockSamplesBinary) return _mockSamplesBinary;
  const items = _makeSamples(MOCK_SAMPLE_COUNT)
    .map((i) => create(ScSampleItemSchema, i));
  _mockSamplesBinary = toBinary(
    InspectionSampleResponseSchema,
    create(InspectionSampleResponseSchema, {
      items,
      total: MOCK_SAMPLE_COUNT,
      waferKey: WAFER_KEY,
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

  // SC dataset info endpoint
  if (
    url.includes("/datasets/" + DATASET_ID) &&
    !url.includes("/inspections") &&
    !url.includes("/annotations")
  ) {
    return new Response(JSON.stringify(MOCK_DATASET), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  // SC bulk annotations endpoint
  if (url.includes("/datasets/" + DATASET_ID + "/annotations/bulk-sc")) {
    return new Response(JSON.stringify({ created: 3 }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  return originalFetch(input, init);
}) as typeof window.fetch;

const mockRouter = createRouter({
  history: createMemoryHistory(),
  routes: [
    {
      path: "/datasets/:id/sc/classify",
      name: "sc-classify",
      component: ReclassifyPage,
    },
  ],
});

mockRouter.push({
  name: "sc-classify",
  params: { id: DATASET_ID },
  query: {
    inspectionTime: INSPECTION_TIME,
    waferKey: String(WAFER_KEY),
  },
});

const meta = {
  component: ReclassifyPage,
  title: "SC/views/ReclassifyPage",
  parameters: {
    backgrounds: { default: "dark" },
    layout: "fullscreen",
  },
  decorators: [
    () => ({
      template:
        '<div style="height:100vh;overflow:hidden;display:flex;flex-direction:column"><story /></div>',
      setup() {
        onUnmounted(() => {
          window.fetch = originalFetch;
        });
        provide(routerKey, mockRouter);
        provide(routeLocationKey, mockRouter.currentRoute.value);
      },
    }),
  ],
} satisfies Meta<typeof ReclassifyPage>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
