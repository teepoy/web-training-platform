import type { Meta, StoryObj } from "@storybook/vue3";
import MarkdownLogWidget from "./MarkdownLogWidget.vue";

const meta = {
  title: "Shared/MarkdownLogWidget",
  component: MarkdownLogWidget,
  args: {
    data: {
      inline: {
        entries: [
          { ts: "10:00:01", level: "info", message: "Started preview session." },
          { ts: "10:00:05", level: "warn", message: "Low confidence on sample s2." },
          { ts: "10:00:09", level: "error", message: "Failed to fetch one thumbnail." },
        ],
      },
    },
    config: {
      maxEntries: 50,
      autoScroll: true,
    },
    size: "normal",
  },
} satisfies Meta<typeof MarkdownLogWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
