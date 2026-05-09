import type { Meta, StoryObj } from "@storybook/vue3";
import { WaferMapWidget } from "@platform/web-ui";
import { providePluginContext } from "../../../.storybook/mocks/pluginContext";

const meta = {
  component: WaferMapWidget,
  title: "Plugins/Sidebar/Wafer Map",
  decorators: [providePluginContext()],
} satisfies Meta<typeof WaferMapWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

const goldenAngle = Math.PI * (3 - Math.sqrt(5));

function generateWaferPoints(count: number, radius: number) {
  return Array.from({ length: count }, (_, i) => {
    const ratio = (i + 0.5) / count;
    const r = Math.sqrt(ratio) * radius;
    const theta = i * goldenAngle;
    return {
      id: `die-${i}`,
      x: +(r * Math.cos(theta)).toFixed(0),
      y: +(r * Math.sin(theta)).toFixed(0),
      value: +(Math.random()).toFixed(2),
    };
  });
}

const smallWaferPoints = generateWaferPoints(200, 150_000_000);

export const Default: Story = {
  args: {
    data: {
      inline: {
        points: smallWaferPoints,
      },
    },
  },
};

export const WithInteraction: Story = {
  args: {
    ...Default.args,
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
