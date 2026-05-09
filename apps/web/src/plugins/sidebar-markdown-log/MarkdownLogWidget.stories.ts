import type { Meta, StoryObj } from "@storybook/vue3";
import { MarkdownLogWidget } from "@platform/web-ui";
import { providePluginContext } from "../../../.storybook/mocks/pluginContext";

const meta = {
  component: MarkdownLogWidget,
  title: "Plugins/Sidebar/Markdown Log",
  decorators: [providePluginContext()],
} satisfies Meta<typeof MarkdownLogWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    data: {
      inline: {
        entries: [
          { ts: "12:00:01", level: "info", message: "Training started" },
          { ts: "12:00:15", level: "info", message: "Epoch 1/10 completed" },
          { ts: "12:01:02", level: "warn", message: "Learning rate decayed to 0.001" },
          { ts: "12:02:30", level: "info", message: "Epoch 5/10 completed" },
          { ts: "12:03:00", level: "error", message: "Validation loss diverged" },
          { ts: "12:03:15", level: "debug", message: "GPU memory: 6.2/8 GB" },
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

export const ErrorsOnly: Story = {
  args: {
    data: {
      inline: {
        entries: [
          { ts: "10:00:01", level: "error", message: "Connection refused: localhost:8000" },
          { ts: "10:00:15", level: "error", message: "Retry attempt 1/3" },
          { ts: "10:00:30", level: "error", message: "Retry attempt 2/3" },
        ],
      },
    },
  },
};
