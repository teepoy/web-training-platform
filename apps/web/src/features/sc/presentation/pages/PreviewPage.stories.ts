import type { Meta, StoryObj } from "@storybook/vue3";
import {
  createRouter,
  createMemoryHistory,
  routerKey,
  routeLocationKey,
} from "vue-router";
import { provide, onUnmounted } from "vue";
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
