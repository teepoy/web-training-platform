export interface ReticleMapOptions {
  xDieCount: number;
  yDieCount: number;
  xDieShift: number;
  yDieShift: number;
}

export const DEFAULT_RETICLE_MAP_OPTIONS: ReticleMapOptions = {
  xDieCount: 3,
  yDieCount: 5,
  xDieShift: 0,
  yDieShift: 0,
};

export function normalizeReticleMapOptions(
  options: ReticleMapOptions,
): ReticleMapOptions {
  return {
    xDieCount: Math.max(
      1,
      Math.floor(
        Number(options.xDieCount) || DEFAULT_RETICLE_MAP_OPTIONS.xDieCount,
      ),
    ),
    yDieCount: Math.max(
      1,
      Math.floor(
        Number(options.yDieCount) || DEFAULT_RETICLE_MAP_OPTIONS.yDieCount,
      ),
    ),
    xDieShift: Math.floor(Number(options.xDieShift) || 0),
    yDieShift: Math.floor(Number(options.yDieShift) || 0),
  };
}
