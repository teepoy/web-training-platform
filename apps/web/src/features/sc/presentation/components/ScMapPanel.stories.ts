import type { Meta, StoryObj } from "@storybook/vue3";
import ScMapPanel from "./ScMapPanel.vue";
import { MIXED_CLASS_POINTS } from "./__tests__/scMapFixtures";

function makeStoryPoints(count: number, width: number, height: number): number[] {
  const points: number[] = [];
  for (let i = 0; i < count; i += 1) {
    points.push(
      (i * 37) % width,
      (i * 53) % height,
      i + 1,
      i % 5,
      i % 3,
      i % 11 === 0 ? 1 : 0,
    );
  }
  return points;
}

const dieSizeX = 8_000;
const dieSizeY = 5_000;
const waferPoints = makeStoryPoints(500, 240_000, 180_000);
const diePoints = makeStoryPoints(500, dieSizeX, dieSizeY);
const reticlePoints = makeStoryPoints(500, dieSizeX * 3, dieSizeY * 5);
const storyDefectIds = Array.from({ length: 500 }, (_, index) => index + 1);
const makeDefectList = (defectIds: number[]) => ({
  $typeName: "sc.v1.DefectList" as const,
  count: defectIds.length,
  defectIds,
});
const storyLegendGroups: Record<string, { $typeName: string; count: number; defectIds: number[] }> =
  storyDefectIds.length > 0 ? Object.fromEntries(
    Array.from({ length: 5 }, (_, classNumber) => [
      String(classNumber),
      makeDefectList(storyDefectIds.filter((id) => (id - 1) % 5 === classNumber)),
    ]),
  ) : {};
const waferGeometry = {
  centerX: 120_000,
  centerY: 90_000,
  originX: 0,
  originY: 0,
  dieSizeX,
  dieSizeY,
};

const meta = {
  component: ScMapPanel,
  title: "SC/components/ScMapPanel",
  tags: ["autodocs"],
  decorators: [
    () => ({
      template: '<div style="height: 600px; width: 600px; background: #0f0f1a; padding: 16px"><story /></div>',
    }),
  ],
} satisfies Meta<typeof ScMapPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const WaferTab: Story = {
  args: {
    activeMapTab: "wafer",
    waferPoints,
    waferFullPoints: waferPoints,
    waferRadiusNm: 120_000,
    waferGeometry,
  },
};

export const DieTab: Story = {
  args: {
    activeMapTab: "die",
    diePoints,
    dieFullPoints: diePoints,
    waferGeometry,
  },
};

export const ReticleTab: Story = {
  args: {
    activeMapTab: "reticle",
    reticlePoints,
    reticleFullPoints: reticlePoints,
    reticleXDieCount: 3,
    reticleYDieCount: 5,
    reticleDieSizeX: dieSizeX,
    reticleDieSizeY: dieSizeY,
    reticleOptions: {
      xDieCount: 3,
      yDieCount: 5,
      xDieShift: 0,
      yDieShift: 0,
    },
    legendSources: ["class", "bin", "annotation", "prediction"],
    legendGroups: storyLegendGroups,
  },
};

export const MixedClasses: Story = {
  args: {
    activeMapTab: "wafer",
    waferPoints: MIXED_CLASS_POINTS,
    waferFullPoints: MIXED_CLASS_POINTS,
  },
};

export const Loading: Story = {
  args: {
    activeMapTab: "wafer",
    mapLoading: true,
  },
};

export const Error: Story = {
  args: {
    activeMapTab: "wafer",
    mapError: "Failed to load map data.",
  },
};

export const Empty: Story = {
  args: {
    activeMapTab: "wafer",
    waferPoints: [],
    waferFullPoints: [],
  },
};

export const SmallContainer600x400: Story = {
  decorators: [
    () => ({
      template: '<div style="height: 400px; width: 600px; background: #0f0f1a; padding: 16px; display: flex; flex-direction: column;"><story /></div>',
    }),
  ],
  args: {
    activeMapTab: "wafer",
    waferPoints: MIXED_CLASS_POINTS,
    waferFullPoints: MIXED_CLASS_POINTS,
  },
};
