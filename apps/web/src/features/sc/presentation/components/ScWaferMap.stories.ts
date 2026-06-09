import type { Meta, StoryObj } from "@storybook/vue3";
import ScWaferMap from "./ScWaferMap.vue";
import { makeStride6Points } from "./__tests__/scMapFixtures";

const WAFER_RADIUS_NM = 150_000_000;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

const meta = {
  component: ScWaferMap,
  title: "SC/components/ScWaferMap",
  tags: ["autodocs"],
  decorators: [
    () => ({
      template:
        '<div style="height:400px;width:600px;background:#0f0f1a;padding:16px"><story /></div>',
    }),
  ],
} satisfies Meta<typeof ScWaferMap>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: { points: makeStride6Points(10), fullPoints: makeStride6Points(10) },
};

export const Empty: Story = {
  args: { points: [], fullPoints: [] },
};
