import type { Meta, StoryObj } from "@storybook/vue3";
import { LabelDistributionWidget } from "@platform/web-ui";
import { providePluginContext } from "../../../.storybook/mocks/pluginContext";

const meta = {
  component: LabelDistributionWidget,
  title: "Plugins/Sidebar/Label Distribution",
  decorators: [
    providePluginContext({
      classifyDashboard: {
        stats: {
          total_samples: 500,
          annotated_samples: 220,
          unlabeled_samples: 280,
          label_counts: {
            cat: 100,
            dog: 80,
            bird: 40,
            fish: 20,
            horse: 15,
          },
        },
      },
    }),
  ],
} satisfies Meta<typeof LabelDistributionWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Horizontal: Story = {
  args: {
    orientation: "horizontal",
  },
};

export const Vertical: Story = {
  args: {
    orientation: "vertical",
  },
};

export const ManyLabels: Story = {
  args: {},
  decorators: [
    providePluginContext({
      classifyDashboard: {
        stats: {
          total_samples: 1000,
          annotated_samples: 1000,
          unlabeled_samples: 0,
          label_counts: Object.fromEntries(
            Array.from({ length: 15 }, (_, i) => [`class_${i}`, 100 - i * 5]),
          ),
        },
      },
    }),
  ],
};

export const WithActiveFilter: Story = {
  args: {},
  decorators: [
    providePluginContext({
      classifyDashboard: {
        stats: {
          total_samples: 300,
          annotated_samples: 300,
          unlabeled_samples: 0,
          label_counts: { cat: 150, dog: 100, bird: 50 },
        },
      },
      interactionState: {
        activeLabelFilter: "cat",
        selectedLabels: ["cat"],
        collections: {},
      },
    }),
  ],
};

export const NoAnnotations: Story = {
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
      },
    }),
  ],
};
