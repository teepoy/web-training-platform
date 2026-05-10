import type { Meta, StoryObj } from "@storybook/vue3";
import WaferMapWidget from "./WaferMapWidget.vue";
import { provideWebUiContext } from "../../storybook/mocks";

const meta = {
  title: "web-ui/widgets/WaferMapWidget",
  component: WaferMapWidget,
  decorators: [provideWebUiContext()],
  args: {
    data: {
      inline: {
        points: [
          { id: "w1", x: -20000000, y: 15000000, value: 1 },
          { id: "w2", x: 10000000, y: -25000000, value: 0.8 },
          { id: "w3", x: 35000000, y: 5000000, value: 0.4 },
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
      maxPoints: 10000,
    },
  },
} satisfies Meta<typeof WaferMapWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
