import type { Meta, StoryObj } from "@storybook/vue3";
import ScReticleMap from "./ScReticleMap.vue";

const defaultPoints = [
  40, 35, 1, 0, 0, 0,
  95, 80, 2, 0, 0, 0,
  160, 120, 3, 0, 0, 0,
  240, 60, 4, 0, 0, 0,
  315, 150, 5, 0, 0, 0,
  410, 95, 6, 0, 0, 0,
];

const meta = {
  component: ScReticleMap,
  title: "SC/components/ScReticleMap",
  tags: ["autodocs"],
  decorators: [
    () => ({
      template:
        '<div style="height:400px;width:600px;background:#0f0f1a;padding:16px"><story /></div>',
    }),
  ],
  args: {
    xDieCount: 6,
    yDieCount: 4,
    dieSizeX: 80,
    dieSizeY: 50,
    points: defaultPoints,
  },
} satisfies Meta<typeof ScReticleMap>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Empty: Story = {
  args: {
    points: [],
  },
};
