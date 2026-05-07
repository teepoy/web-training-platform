import type { Meta, StoryObj } from "@storybook/vue3";
import DataTableWidget from "./DataTableWidget.vue";
import { providePluginContext } from "../../../.storybook/mocks/pluginContext";

const meta = {
  component: DataTableWidget,
  title: "Plugins/Sidebar/Data Table",
  decorators: [providePluginContext()],
} satisfies Meta<typeof DataTableWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const LegacyTable: Story = {
  args: {
    data: {
      inline: {
        columns: ["Name", "Type", "Size"],
        rows: [
          ["image_001.jpg", "image", "2.4 MB"],
          ["image_002.png", "image", "1.8 MB"],
          ["data.csv", "csv", "512 KB"],
          ["model.pth", "model", "45 MB"],
        ],
      },
    },
  },
};

export const InteractiveTable: Story = {
  args: {
    data: {
      inline: {
        columns: [
          { key: "id", label: "ID" },
          { key: "label", label: "Label" },
          { key: "score", label: "Score" },
        ],
        rows: [
          { id: "s1", cells: { id: "s1", label: "cat", score: 0.95 } },
          { id: "s2", cells: { id: "s2", label: "dog", score: 0.88 } },
          { id: "s3", cells: { id: "s3", label: "bird", score: 0.72 } },
        ],
      },
    },
    config: {
      interaction: {
        collection: "samples",
        entity: "sample",
        emitSelection: true,
      },
    },
  },
};

export const Compact: Story = {
  args: {
    ...LegacyTable.args,
    size: "compact",
  },
};

export const Large: Story = {
  args: {
    ...LegacyTable.args,
    size: "large",
  },
};

export const Empty: Story = {
  args: {
    data: null,
  },
};

export const ManyRows: Story = {
  args: {
    data: {
      inline: {
        columns: ["#", "Name", "Value"],
        rows: Array.from({ length: 50 }, (_, i) => [
          String(i + 1),
          `Item ${i + 1}`,
          `${(Math.random() * 100).toFixed(1)}`,
        ]),
      },
    },
  },
};
