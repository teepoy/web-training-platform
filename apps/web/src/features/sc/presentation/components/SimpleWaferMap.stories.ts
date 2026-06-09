import type { Meta, StoryObj } from "@storybook/vue3";
import SimpleWaferMap from "./SimpleWaferMap.vue";
import type { SimpleMapPoint } from "./SimpleMapPoint";

const NM = 1_000_000;

function makePoints(count: number): SimpleMapPoint[] {
  const labels = ["scratch", "particle", "void"];
  const points: SimpleMapPoint[] = [];
  for (let i = 0; i < count; i++) {
    const angle = (i * 2.39996) % (Math.PI * 2);
    const r = 80 * NM + (i * 3 * NM) % (60 * NM);
    points.push({
      x: Math.cos(angle) * r,
      y: Math.sin(angle) * r,
      id: i + 1,
      label: labels[i % labels.length],
      hasImageFlag: i % 9 === 0,
      isSelectedFlag: i % 17 === 0,
    });
  }
  return points;
}

function makePointsInViewport(
  count: number,
  vp: { x: number; y: number; w: number; h: number },
): SimpleMapPoint[] {
  const labels = ["scratch", "particle", "void"];
  const points: SimpleMapPoint[] = [];
  for (let i = 0; i < count; i++) {
    points.push({
      x: vp.x + vp.w * ((i * 0.37 + 0.1) % 0.9),
      y: vp.y + vp.h * ((i * 0.53 + 0.1) % 0.9),
      id: i + 1,
      label: labels[i % labels.length],
      hasImageFlag: i % 9 === 0,
      isSelectedFlag: i % 17 === 0,
    });
  }
  return points;
}

const defaultColorMap: Record<string, string> = {
  scratch: "#e74c3c",
  particle: "#3498db",
  void: "#2ecc71",
};

const meta = {
  component: SimpleWaferMap,
  title: "SC/components/SimpleWaferMap",
  tags: ["autodocs"],
  decorators: [
    () => ({
      template:
        '<div style="height:400px;width:600px;background:#0f0f1a;padding:16px"><story /></div>',
    }),
  ],
} satisfies Meta<typeof SimpleWaferMap>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: { points: makePoints(200), colorMap: defaultColorMap },
};

export const Empty: Story = {
  args: { points: [], colorMap: {} },
};

export const WithSelected: Story = {
  args: {
    points: makePoints(80).map((p, i) => ({ ...p, isSelectedFlag: i < 10 })),
    colorMap: defaultColorMap,
  },
};

export const WithImages: Story = {
  args: {
    points: makePoints(80).map((p) => ({ ...p, hasImageFlag: true })),
    colorMap: defaultColorMap,
  },
};

export const Dense: Story = {
  args: { points: makePoints(800), colorMap: defaultColorMap },
};

export const GridOnly: Story = {
  name: "Grid (few points)",
  args: {
    points: makePoints(20).map((p, i) => ({ ...p, isSelectedFlag: i < 3, hasImageFlag: i % 5 === 0 })),
    colorMap: defaultColorMap,
  },
};

export const Zoomed: Story = {
  name: "Zoomed (60M × 60M viewport)",
  args: {
    points: makePointsInViewport(60, { x: -30_000_000, y: -30_000_000, w: 60_000_000, h: 60_000_000 })
      .map((p, i) => ({ ...p, isSelectedFlag: i < 5, hasImageFlag: i % 5 === 0 })),
    colorMap: defaultColorMap,
    zoom: { x: -30_000_000, y: -30_000_000, w: 60_000_000, h: 60_000_000 },
  },
};

export const ZoomedNearNotch: Story = {
  name: "Zoomed near notch",
  args: {
    points: makePointsInViewport(60, { x: -30_000_000, y: -180_000_000, w: 60_000_000, h: 60_000_000 })
      .map((p, i) => ({ ...p, isSelectedFlag: i < 5, hasImageFlag: i % 5 === 0 })),
    colorMap: defaultColorMap,
    zoom: { x: -30_000_000, y: -180_000_000, w: 60_000_000, h: 60_000_000 },
  },
};
