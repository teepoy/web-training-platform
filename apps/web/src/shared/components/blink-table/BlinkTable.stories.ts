import type { Meta, StoryObj } from "@storybook/vue3";
import BlinkTable from "./BlinkTable.vue";
import { multiImageRows, multiImageColumns } from "./multiImageFixture";
import { blinkRows, extraColumns } from "./fixtures";

const meta = {
  title: "web-ui/components/BlinkTable",
  component: BlinkTable,
  decorators: [
    () => ({
      template: '<div style="height: 500px"><story /></div>',
    }),
  ],
  args: {
    rows: multiImageRows,
    columns: multiImageColumns,
  },
} satisfies Meta<typeof BlinkTable>;

export default meta;
type Story = StoryObj<typeof meta>;

export const MultiImageSeed: Story = {};

export const BlinkDisabled: Story = {
  args: {
    initialBlinkEnabled: false,
  },
};

export const OriginalPicsum: Story = {
  args: {
    rows: blinkRows,
    columns: extraColumns,
  },
};
