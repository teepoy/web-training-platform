import type { Meta, StoryObj } from "@storybook/vue3";
import SimpleReticleMap from "./SimpleReticleMap.vue";
import type { SimpleMapPoint } from "./SimpleMapPoint";

function makePoints(count: number): SimpleMapPoint[] {
  const labels = ["defect_a", "defect_b", "defect_c", "defect_d"];
  const points: SimpleMapPoint[] = [];
  for (let i = 0; i < count; i++) {
    points.push({
      x: 80 + (i * 37) % 720,
      y: 60 + (i * 53) % 480,
      id: i + 1,
      label: labels[i % labels.length],
      hasImageFlag: i % 7 === 0,
      isSelectedFlag: i % 13 === 0,
    });
  }
  return points;
}

const defaultColorMap: Record<string, string> = {
  defect_a: "#e74c3c",
  defect_b: "#3498db",
  defect_c: "#2ecc71",
  defect_d: "#9b59b6",
};

const meta = {
  component: SimpleReticleMap,
  title: "SC/components/SimpleReticleMap",
  tags: ["autodocs"],
  decorators: [
    () => ({
      template:
        '<div style="height:400px;width:600px;background:#0f0f1a;padding:16px"><story /></div>',
    }),
  ],
} satisfies Meta<typeof SimpleReticleMap>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: { points: makePoints(80), colorMap: defaultColorMap },
};

export const Empty: Story = {
  args: { points: [], colorMap: {} },
};

export const WithSelected: Story = {
  args: {
    points: makePoints(40).map((p, i) => ({ ...p, isSelectedFlag: i < 6 })),
    colorMap: defaultColorMap,
  },
};

export const WithImages: Story = {
  args: {
    points: makePoints(40).map((p) => ({ ...p, hasImageFlag: true })),
    colorMap: defaultColorMap,
  },
};

export const FewPoints: Story = {
  args: {
    points: [
      { x: 200, y: 120, id: 1, label: "defect_a", hasImageFlag: false, isSelectedFlag: false },
      { x: 400, y: 240, id: 2, label: "defect_b", hasImageFlag: true, isSelectedFlag: false },
      { x: 600, y: 360, id: 3, label: "defect_c", hasImageFlag: false, isSelectedFlag: true },
    ],
    colorMap: defaultColorMap,
  },
};

export const Zoomed: Story = {
  name: "Zoomed (300×200 viewport)",
  args: {
    points: makePoints(40).map((p, i) => ({ ...p, isSelectedFlag: i < 5, hasImageFlag: i % 5 === 0 })),
    colorMap: defaultColorMap,
    zoom: { x: 200, y: 100, w: 300, h: 200 },
  },
};
