import type { ReticleMapOptions } from "@/features/sc/application/reticleMapOptions";

export type PerspectiveExpressions = Record<string, string>;

export interface ReticleExpressionGeometry {
  dieSizeX: number;
  dieSizeY: number;
}

function positiveModulo(column: "index_x" | "index_y", shift: number, count: number): string {
  return `((("${column}" + ${shift}) % ${count}) + ${count}) % ${count}`;
}

export function perspectiveReticleExpressions(
  options: ReticleMapOptions,
  geometry: ReticleExpressionGeometry,
): PerspectiveExpressions {
  if (!(geometry.dieSizeX > 0) || !(geometry.dieSizeY > 0)) {
    throw new Error("Reticle expressions require positive die dimensions");
  }
  return {
    reticle_x: `"die_x" + (${positiveModulo("index_x", options.xDieShift, options.xDieCount)} * ${geometry.dieSizeX})`,
    reticle_y: `"die_y" + (${positiveModulo("index_y", options.yDieShift, options.yDieCount)} * ${geometry.dieSizeY})`,
  };
}
