import type { Meta, StoryObj } from "@storybook/vue3";
import BlinkTable from "./BlinkTable.vue";
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
    rows: blinkRows,
    columns: extraColumns,
  },
} satisfies Meta<typeof BlinkTable>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const BlinkDisabled: Story = {
  args: {
    initialBlinkEnabled: false,
  },
};
