import type { Meta, StoryObj } from "@storybook/vue3";
import WaferMapWidget from "./WaferMapWidget.vue";
import { provideWebUiContext } from "../../storybook/mocks";

const DEFAULT_WAFER_RADIUS_NM = 150_000_000;

function generateGoldenAnglePoints(count: number): Array<{ id: string; x: number; y: number; value: number }> {
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  const points: Array<{ id: string; x: number; y: number; value: number }> = [];
  for (let i = 0; i < count; i++) {
    const ratio = (i + 0.5) / count;
    const r = Math.sqrt(ratio) * DEFAULT_WAFER_RADIUS_NM;
    const theta = i * goldenAngle;
    points.push({
      id: `p-${i}`,
      x: r * Math.cos(theta),
      y: r * Math.sin(theta),
      value: 1,
    });
  }
  return points;
}

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

export const WithDieGrid: Story = {
  args: {
    data: {
      inline: {
        points: generateGoldenAnglePoints(500),
      },
    },
    config: {
      dieGrid: {
        dieWidthNm: 6_000_000,
        dieHeightNm: 3_000_000,
        originX: 0,
        originY: 0,
      },
    },
  },
};

export const SmallScatter: Story = {
  args: {
    data: {
      inline: {
        points: generateGoldenAnglePoints(500),
      },
    },
    config: {
      scatterSize: 1,
    },
  },
};
