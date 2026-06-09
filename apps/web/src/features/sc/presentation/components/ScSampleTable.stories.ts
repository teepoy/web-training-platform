import type { Meta, StoryObj } from "@storybook/vue3";
import ScSampleTable from "./ScSampleTable.vue";
import type { ScSampleItem } from "@/features/sc/generated/proto/sc/v1/sample_pb";

const INSPECTION_TIME_BIGINT = BigInt(Math.floor(new Date("2025-01-15T10:30:00").getTime() / 1000));
const WAFER_KEY = 1;

function makeSamples(count: number): ScSampleItem[] {
  return Array.from({ length: count }, (_, i) => ({
    defectId: i + 1,
    waferX: -80_000_000 + Math.round(Math.random() * 160_000_000),
    waferY: -80_000_000 + Math.round(Math.random() * 160_000_000),
    roughBin: (i % 5) + 1,
    classNumber: i % 3 === 0 ? undefined : (i % 4) + 1,
    inspectionTime: INSPECTION_TIME_BIGINT,
    waferKey: WAFER_KEY,
    reviewImages: [],
  }));
}

const meta = {
  component: ScSampleTable,
  title: "SC/components/ScSampleTable",
  tags: ["autodocs"],
  decorators: [
    () => ({
      template: '<div style="height:400px;display:flex;flex-direction:column"><story /></div>',
    }),
  ],
} satisfies Meta<typeof ScSampleTable>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: { samples: makeSamples(200), loading: false, total: 200 },
};

export const Empty: Story = {
  args: { samples: [], loading: false, total: 0 },
};

export const Loading: Story = {
  args: { samples: [], loading: true, total: 0 },
};
