import type { Meta, StoryObj } from "@storybook/vue3";
import { InteractiveScatterWidget } from "@platform/web-ui";
import { providePluginContext } from "../../../.storybook/mocks/pluginContext";

const meta = {
  component: InteractiveScatterWidget,
  title: "Plugins/Sidebar/Interactive Scatter",
  decorators: [providePluginContext()],
} satisfies Meta<typeof InteractiveScatterWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

function generatePoints(count: number) {
  const labels = ["cat", "dog", "bird"];
  return Array.from({ length: count }, (_, i) => ({
    id: `point-${i}`,
    x: +(Math.random() * 10).toFixed(3),
    y: +(Math.random() * 10).toFixed(3),
    label: labels[i % labels.length],
  }));
}

export const Default: Story = {
  args: {
    data: {
      inline: {
        points: generatePoints(30),
      },
    },
    config: {
      interaction: {
        collection: "samples",
        entity: "sample",
        emitSelection: true,
        filterFromSelection: true,
      },
    },
  },
};

export const FewPoints: Story = {
  args: {
    data: {
      inline: {
        points: [
          { id: "a1", x: 1.2, y: 3.4, label: "alpha" },
          { id: "a2", x: 2.5, y: 6.1, label: "alpha" },
          { id: "b1", x: 4.0, y: 5.5, label: "beta" },
          { id: "b2", x: 5.2, y: 2.1, label: "beta" },
          { id: "c1", x: 7.8, y: 8.3, label: null },
        ],
      },
    },
  },
};

export const Compact: Story = {
  args: {
    ...Default.args,
    size: "compact",
  },
};

export const Large: Story = {
  args: {
    ...Default.args,
    size: "large",
  },
};

export const Empty: Story = {
  args: {
    data: null,
  },
};
