/**
 * Converts Arrow columnar data to STRIDE=6 flat display arrays for map rendering.
 * Format: [x, y, defect_id, class, rough_bin, has_review, ...]
 */
export function columnsToDisplayArrays(data: Record<string, unknown[]>): {
  wafer: number[];
  die: number[];
  reticle: number[];
} {
  const defectIds = data.defect_id as number[];
  const waferX = data.wafer_x as number[];
  const waferY = data.wafer_y as number[];
  const dieX = data.die_x as number[];
  const dieY = data.die_y as number[];
  const reticleX = data.reticle_x as number[];
  const reticleY = data.reticle_y as number[];
  const classes = data.class as number[];
  const roughBins = data.rough_bin as number[];
  const imagesCounts = (data.images_count as number[] | undefined) ?? [];

  const n = defectIds?.length ?? 0;

  const wafer = new Array<number>(n * 6);
  const die = new Array<number>(n * 6);
  const reticle = new Array<number>(n * 6);

  for (let i = 0; i < n; i++) {
    const hasReview = (imagesCounts[i] ?? 0) > 0 ? 1 : 0;
    const wi = i * 6;

    wafer[wi] = waferX[i] ?? 0;
    wafer[wi + 1] = waferY[i] ?? 0;
    wafer[wi + 2] = defectIds[i] ?? 0;
    wafer[wi + 3] = classes[i] ?? 0;
    wafer[wi + 4] = roughBins[i] ?? 0;
    wafer[wi + 5] = hasReview;

    die[wi] = dieX[i] ?? 0;
    die[wi + 1] = dieY[i] ?? 0;
    die[wi + 2] = defectIds[i] ?? 0;
    die[wi + 3] = classes[i] ?? 0;
    die[wi + 4] = roughBins[i] ?? 0;
    die[wi + 5] = hasReview;

    reticle[wi] = reticleX[i] ?? 0;
    reticle[wi + 1] = reticleY[i] ?? 0;
    reticle[wi + 2] = defectIds[i] ?? 0;
    reticle[wi + 3] = classes[i] ?? 0;
    reticle[wi + 4] = roughBins[i] ?? 0;
    reticle[wi + 5] = hasReview;
  }

  return { wafer, die, reticle };
}
