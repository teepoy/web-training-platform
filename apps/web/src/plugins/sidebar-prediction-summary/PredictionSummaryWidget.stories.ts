import type { Meta, StoryObj } from "@storybook/vue3";
import { provide, computed } from "vue";
import PredictionSummaryWidget from "./PredictionSummaryWidget.vue";
import { providePluginContext } from "../../../.storybook/mocks/pluginContext";

const withPredictionItems: typeof meta.decorators[number] = (story) => ({
  components: { story },
  setup() {
    provide(
      "pr-grid-items",
      computed(() => [
        {
          id: "p1",
          predictionLabel: "cat",
          predictionConfidence: 0.92,
          draftLabel: null,
        },
        {
          id: "p2",
          predictionLabel: "dog",
          predictionConfidence: 0.85,
          draftLabel: "cat",
        },
        {
          id: "p3",
          predictionLabel: "bird",
          predictionConfidence: 0.78,
          draftLabel: null,
        },
        {
          id: "p4",
          predictionLabel: "cat",
          predictionConfidence: 0.95,
          draftLabel: null,
        },
        {
          id: "p5",
          predictionLabel: "dog",
          predictionConfidence: 0.6,
          draftLabel: "bird",
        },
      ]),
    );
    return {};
  },
  template: "<story />",
});

const meta = {
  component: PredictionSummaryWidget,
  title: "Plugins/Sidebar/Prediction Summary",
  decorators: [providePluginContext()],
} satisfies Meta<typeof PredictionSummaryWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const WithPredictions: Story = {
  args: {},
  decorators: [withPredictionItems],
};

export const Empty: Story = {
  args: {},
};
