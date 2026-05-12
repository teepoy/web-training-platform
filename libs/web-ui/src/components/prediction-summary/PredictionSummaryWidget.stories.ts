import type { Meta, StoryObj } from "@storybook/vue3";
import PredictionSummaryWidget from "./PredictionSummaryWidget.vue";
import { provideWebUiContext } from "../../storybook/mocks";

const meta = {
  title: "web-ui/widgets/PredictionSummaryWidget",
  component: PredictionSummaryWidget,
  decorators: [
    provideWebUiContext({
      predictionGridItems: [
        { id: "p1", predictionLabel: "cat", predictionConfidence: 0.91 },
        { id: "p2", predictionLabel: "dog", draftLabel: "cat", predictionConfidence: 0.74 },
      ],
    }),
  ],
} satisfies Meta<typeof PredictionSummaryWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
