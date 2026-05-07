import type { Meta, StoryObj } from "@storybook/vue3";
import BrowserSummaryWidget from "./BrowserSummaryWidget.vue";
import { providePluginContext } from "../../../.storybook/mocks/pluginContext";

const meta = {
  component: BrowserSummaryWidget,
  title: "Plugins/Sidebar/Browser Summary",
  decorators: [providePluginContext()],
} satisfies Meta<typeof BrowserSummaryWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    totalLoaded: 500,
    filteredCount: 350,
  },
};

export const NoFilter: Story = {
  args: {
    totalLoaded: 200,
  },
};

export const WithActiveFilter: Story = {
  args: {
    totalLoaded: 1000,
    filteredCount: 120,
  },
  decorators: [
    providePluginContext({
      interactionState: {
        activeLabelFilter: "cat",
        selectedLabels: ["cat"],
        collections: {},
      },
    }),
  ],
};

export const Empty: Story = {
  args: {},
};
