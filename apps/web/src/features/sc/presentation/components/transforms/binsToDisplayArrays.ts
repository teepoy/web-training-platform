import type { MapBinRow } from "../composables/usePerspectiveMapView";

export function binsToDisplayArray(bins: MapBinRow[], _legendCol: string): number[] {
  const n = bins.length;
  const out = new Array<number>(n * 6);

  for (let i = 0; i < n; i++) {
    const bin = bins[i];
    const x = bin.gx * bin.binSize + bin.binSize / 2;
    const y = bin.gy * bin.binSize + bin.binSize / 2;

    const wi = i * 6;
    out[wi] = x;
    out[wi + 1] = y;
    out[wi + 2] = Number(bin[bin._legendCol] ?? 0);
    out[wi + 3] = (bin.map_in_selection as number | undefined) ?? 0;
    out[wi + 4] = (bin.images_has_review as number | undefined) ?? 0;
    out[wi + 5] = (bin.gallery_in_selection as number | undefined) ?? 0;
  }

  return out;
}
