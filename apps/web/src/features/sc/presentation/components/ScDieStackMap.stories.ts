import type { Meta, StoryObj } from "@storybook/vue3";
import ScDieStackMap from "./ScDieStackMap.vue";
import { makeStride6Points } from "./__tests__/scMapFixtures";

const defaultPoints = makeStride6Points(10000);

const meta = {
  component: ScDieStackMap,
  title: "SC/components/ScDieStackMap",
  tags: ["autodocs"],
  decorators: [
    () => ({
      template:
        '<div style="height:400px;width:600px;background:#0f0f1a;padding:16px"><story /></div>',
    }),
  ],
} satisfies Meta<typeof ScDieStackMap>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    points: defaultPoints,
  },
};

export const Empty: Story = {
  args: { points: [] },
};
