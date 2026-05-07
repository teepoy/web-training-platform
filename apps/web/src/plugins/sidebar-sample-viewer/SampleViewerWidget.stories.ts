import type { Meta, StoryObj } from "@storybook/vue3";
import SampleViewerWidget from "./SampleViewerWidget.vue";
import { providePluginContext } from "../../../.storybook/mocks/pluginContext";

const meta = {
  component: SampleViewerWidget,
  title: "Plugins/Sidebar/Sample Viewer",
  decorators: [providePluginContext()],
} satisfies Meta<typeof SampleViewerWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const WithIds: Story = {
  args: {
    data: {
      inline: {
        sampleIds: ["img-001", "img-002", "img-003", "img-004"],
        mode: "grid",
      },
    },
  },
};

export const WithLabels: Story = {
  args: {
    data: {
      inline: {
        sampleIds: ["s-1", "s-2", "s-3"],
        mode: "grid",
        samples: [
          { id: "s-1", label: "cat" },
          { id: "s-2", label: "dog" },
          { id: "s-3", label: "bird" },
        ],
      },
    },
  },
};

export const ListView: Story = {
  args: {
    data: {
      inline: {
        sampleIds: ["s-1", "s-2", "s-3"],
        mode: "list",
      },
    },
  },
};

export const Compact: Story = {
  args: {
    ...WithIds.args,
    size: "compact",
  },
};

export const Empty: Story = {
  args: {
    data: null,
  },
};
