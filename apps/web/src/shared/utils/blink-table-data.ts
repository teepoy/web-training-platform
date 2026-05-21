import type { BlinkRow, BlinkColumnDef } from "../types/blink-table";

export interface BlinkSampleInput {
  id: string;
  imageSrcs: string[];
  metadata: Record<string, unknown>;
  label?: string;
}

export interface BuildBlinkTableDataOptions {
  maxImageColumns?: number;
  extraColumns?: BlinkColumnDef[];
}

export interface BlinkTableDataResult {
  rows: BlinkRow[];
  columns: BlinkColumnDef[];
}

const DEFAULT_MAX_IMAGE_COLUMNS = 6;

export function buildBlinkTableData(
  samples: BlinkSampleInput[],
  options: BuildBlinkTableDataOptions = {},
): BlinkTableDataResult {
  const maxImageColumns =
    options.maxImageColumns ?? DEFAULT_MAX_IMAGE_COLUMNS;
  const extraColumns = options.extraColumns ?? [];

  const rows: BlinkRow[] = samples.map((sample) => {
    const uris = sample.imageSrcs;
    const imageA = uris[0] ?? "";
    const imageB = uris[1] ?? "";

    const cells: Record<string, string> = {
      sample_id: sample.id.slice(0, 12),
      image_count: String(uris.length),
    };

    for (let i = 0; i < maxImageColumns; i++) {
      cells[`img_${i}`] = uris[i] ?? "";
    }

    if (sample.label) {
      cells["label"] = sample.label;
    }

    // Merge extra column defaults (empty string if no cell value)
    for (const col of extraColumns) {
      if (!(col.key in cells)) {
        cells[col.key] = "";
      }
    }

    return {
      id: sample.id,
      imageA,
      imageB,
      metadata: sample.metadata,
      cells,
    };
  });

  const imageCols: BlinkColumnDef[] = [];
  for (let i = 0; i < maxImageColumns; i++) {
    imageCols.push({
      key: `img_${i}`,
      title: `Image ${i + 1}`,
      kind: "image",
      width: 120,
    });
  }

  const baseColumns: BlinkColumnDef[] = [
    { key: "sample_id", title: "Sample ID", width: 130 },
    ...(samples.some((s) => s.label) ? [{ key: "label", title: "Label" }] : []),
    { key: "image_count", title: "Images", width: 70 },
  ];

  const columns: BlinkColumnDef[] = [
    ...baseColumns,
    ...imageCols,
    ...extraColumns,
  ];

  return { rows, columns };
}
