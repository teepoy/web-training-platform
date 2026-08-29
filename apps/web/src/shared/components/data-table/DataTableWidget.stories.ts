import type { Meta, StoryObj } from "@storybook/vue3";
import DataTableWidget from "./DataTableWidget.vue";
import { provideWebUiContext } from "../../../../.storybook/support/mocks";

const meta = {
  title: "Shared/DataTableWidget",
  component: DataTableWidget,
  decorators: [provideWebUiContext()],
  args: {
    data: {
      inline: {
        columns: ["name", "label", "score"],
        rows: [
          ["sample-1", "cat", 0.98],
          ["sample-2", "dog", 0.87],
        ],
      },
    },
    config: {
      maxRows: 100,
      striped: true,
    },
    size: "normal",
  },
} satisfies Meta<typeof DataTableWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
