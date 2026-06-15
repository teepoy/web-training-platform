import type { Meta, StoryObj } from "@storybook/vue3";
import {
  createRouter,
  createMemoryHistory,
  routerKey,
  routeLocationKey,
} from "vue-router";
import { provide, onUnmounted } from "vue";
import ReclassifyPage from "./ReclassifyPage.vue";

const DATASET_ID = "mock-sc-dataset-1";
const INSPECTION_TIME = "2025-01-15T10:30:00";
const WAFER_KEY = 1;

const MOCK_DATASET = {
  id: DATASET_ID,
  name: "Patch_LOT-2026-001_WAF-001_2026-05-26-08-00-00.000000",
  label_space: ["Normal", "Scratch", "Particle", "Crack", "Void"],
  task_spec: { task_type: "patch" },
};




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
