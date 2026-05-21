import type { Meta, StoryObj } from "@storybook/vue3";
import BrowserSummaryWidget from "./BrowserSummaryWidget.vue";
import { provideWebUiContext } from "../../storybook/mocks";

const meta = {
  title: "web-ui/widgets/BrowserSummaryWidget",
  component: BrowserSummaryWidget,
  decorators: [provideWebUiContext()],
  args: {
    totalLoaded: 128,
    filteredCount: 96,
  },
} satisfies Meta<typeof BrowserSummaryWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
