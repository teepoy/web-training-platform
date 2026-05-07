import type { Meta, StoryObj } from "@storybook/vue3";
import AnnotationProgressWidget from "./AnnotationProgressWidget.vue";
import { providePluginContext } from "../../../.storybook/mocks/pluginContext";

const meta = {
  component: AnnotationProgressWidget,
  title: "Plugins/Sidebar/Annotation Progress",
  decorators: [
    providePluginContext({
      classifyDashboard: {
        stats: {
          total_samples: 500,
          annotated_samples: 220,
          unlabeled_samples: 280,
          label_counts: { cat: 100, dog: 80, bird: 40 },
        },
        draftCount: 15,
        selectedCount: 3,
      },
    }),
  ],
} satisfies Meta<typeof AnnotationProgressWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {},
};

export const Bar: Story = {
  args: {
    chartType: "bar",
  },
};

export const NoDrafts: Story = {
  args: {
    includeDrafts: false,
  },
};

export const Compact: Story = {
  args: {
    size: "compact",
  },
};

export const NoLabels: Story = {
  args: {},
  decorators: [
    providePluginContext({
      classifyDashboard: {
        stats: {
          total_samples: 100,
          annotated_samples: 0,
          unlabeled_samples: 100,
          label_counts: {},
        },
        draftCount: 0,
        selectedCount: 0,
      },
    }),
  ],
};
