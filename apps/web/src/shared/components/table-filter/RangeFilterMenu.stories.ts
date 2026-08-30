import type { Meta, StoryObj } from "@storybook/vue3";
import RangeFilterMenu from "./RangeFilterMenu.vue";

const meta = {
  title: "Shared/TableFilter/RangeFilterMenu",
  component: RangeFilterMenu,
  parameters: { layout: "centered" },
  args: {
    descriptor: {
      kind: "number",
      bounds: { min: -25.5, max: 120.75 },
      step: 0.001,
      displayPrecision: 3,
    },
    min: 12.34567,
    max: 86.54321,
  },
} satisfies Meta<typeof RangeFilterMenu>;

export default meta;
type Story = StoryObj<typeof meta>;

export const NumericWithObservedBounds: Story = {};

export const DateTimeHalfOpenInterval: Story = {
  args: {
    descriptor: {
      kind: "datetime",
      timeZone: "browser",
      interval: "[start,end)",
    },
    min: new Date(2026, 7, 1, 8, 0).getTime(),
    max: new Date(2026, 7, 7, 18, 0).getTime(),
  },
};

export const MissingObservedBounds: Story = {
  args: {
    descriptor: {
      kind: "number",
      bounds: null,
      step: 1,
      displayPrecision: 0,
    },
    min: 10,
    max: 20,
    rangeUnavailable: true,
  },
};
