import type { Meta, StoryObj } from "@storybook/vue3";
import LabelDistributionWidget from "./LabelDistributionWidget.vue";
import { provideWebUiContext } from "../../storybook/mocks";

const meta = {
  title: "web-ui/widgets/LabelDistributionWidget",
  component: LabelDistributionWidget,
  decorators: [provideWebUiContext()],
  args: {
    orientation: "horizontal",
    showValues: true,
    maxBars: 20,
  },
} satisfies Meta<typeof LabelDistributionWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Vertical: Story = {
  args: {
    orientation: "vertical",
  },
};
