import type { Meta, StoryObj } from "@storybook/vue3";
import AnnotationProgressWidget from "./AnnotationProgressWidget.vue";
import { provideWebUiContext } from "../../../../.storybook/support/mocks";

const meta = {
  title: "Shared/AnnotationProgressWidget",
  component: AnnotationProgressWidget,
  decorators: [provideWebUiContext()],
  args: {
    chartType: "donut",
    includeDrafts: true,
    showCounts: true,
    showPercent: true,
    showLabelBreakdown: true,
  },
} satisfies Meta<typeof AnnotationProgressWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const BarMode: Story = {
  args: {
    chartType: "bar",
  },
};
