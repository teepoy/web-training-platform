import type { Meta, StoryObj } from "@storybook/vue3";
import { defineComponent } from "vue";
import WidgetErrorBoundary from "./WidgetErrorBoundary.vue";

const ThrowingChild = defineComponent({
  setup() {
    throw new Error("Simulated widget crash");
  },
  template: "<div/>",
});

const meta = {
  title: "web-ui/components/WidgetErrorBoundary",
  component: WidgetErrorBoundary,
  args: {
    widgetId: "test-widget",
    widgetComponent: "TestWidget",
  },
} satisfies Meta<typeof WidgetErrorBoundary>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: (args) => ({
    components: { WidgetErrorBoundary },
    setup: () => ({ args }),
    template: `
      <WidgetErrorBoundary v-bind="args">
        <div>Child content</div>
      </WidgetErrorBoundary>
    `,
  }),
};

export const ErrorCaptured: Story = {
  render: (args) => ({
    components: { WidgetErrorBoundary, ThrowingChild },
    setup: () => ({ args }),
    template: `
      <WidgetErrorBoundary v-bind="args">
        <ThrowingChild />
      </WidgetErrorBoundary>
    `,
  }),
};
