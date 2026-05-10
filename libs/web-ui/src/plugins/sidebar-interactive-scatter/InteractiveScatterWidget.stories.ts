import type { Meta, StoryObj } from "@storybook/vue3";
import InteractiveScatterWidget from "./InteractiveScatterWidget.vue";
import { provideWebUiContext } from "../../storybook/mocks";

const meta = {
  title: "web-ui/widgets/InteractiveScatterWidget",
  component: InteractiveScatterWidget,
  decorators: [provideWebUiContext()],
  args: {
    data: {
      inline: {
        points: [
          { id: "s1", x: 10, y: 20, label: "cat" },
          { id: "s2", x: 30, y: 15, label: "dog" },
          { id: "s3", x: 25, y: 35, label: "bird" },
        ],
      },
    },
    config: {
      interaction: {
        collection: "samples",
        entity: "sample",
        emitSelection: true,
        filterFromSelection: true,
      },
    },
  },
} satisfies Meta<typeof InteractiveScatterWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
