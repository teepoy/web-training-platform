import type { Meta, StoryObj } from "@storybook/vue3";
import SimpleDieStackMap from "./SimpleDieStackMap.vue";
import type { SimpleMapPoint } from "./SimpleMapPoint";

function makePoints(count: number): SimpleMapPoint[] {
  const labels = ["scratch", "particle", "void", "crack"];
  const points: SimpleMapPoint[] = [];
  for (let i = 0; i < count; i++) {
    points.push({
      x: (Math.sin(i * 1.7) * 40 + 50) + (Math.random() - 0.5) * 20,
      y: (Math.cos(i * 2.3) * 30 + 50) + (Math.random() - 0.5) * 15,
      id: i + 1,
      label: labels[i % labels.length],
      hasImageFlag: i % 7 === 0,
      isSelectedFlag: i % 11 === 0,
    });
  }
  return points;
}

const defaultColorMap: Record<string, string> = {
  scratch: "#e74c3c",
  particle: "#3498db",
  void: "#2ecc71",
  crack: "#f39c12",
};

const meta = {
  component: SimpleDieStackMap,
  title: "SC/components/SimpleDieStackMap",
  tags: ["autodocs"],
  decorators: [
    () => ({
      template:
        '<div style="height:400px;width:600px;background:#0f0f1a;padding:16px"><story /></div>',
    }),
  ],
} satisfies Meta<typeof SimpleDieStackMap>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: { points: makePoints(60), colorMap: defaultColorMap },
};

export const Empty: Story = {
  args: { points: [], colorMap: {} },
};

export const SingleLabel: Story = {
  args: {
    points: makePoints(40).map((p) => ({ ...p, label: "scratch" })),
    colorMap: { scratch: "#e74c3c" },
  },
};

export const WithSelected: Story = {
  args: {
    points: makePoints(30).map((p, i) => ({ ...p, isSelectedFlag: i < 5 })),
    colorMap: defaultColorMap,
  },
};

export const WithImages: Story = {
  args: {
    points: makePoints(30).map((p) => ({ ...p, hasImageFlag: true })),
    colorMap: defaultColorMap,
  },
};

export const Zoomed: Story = {
  name: "Zoomed (40×30 viewport)",
  args: {
    points: makePoints(40).map((p, i) => ({ ...p, isSelectedFlag: i < 5, hasImageFlag: i % 5 === 0 })),
    colorMap: defaultColorMap,
    zoom: { x: 30, y: 30, w: 40, h: 30 },
  },
};
