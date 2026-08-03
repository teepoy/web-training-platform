import type { ScSampleTableDisplayRow } from "@/features/sc/domain/workbenchInteraction";

export interface ScFilterColumnDefinition {
  key: string;
  title: string;
  filter: "set" | "range";
}

export interface ScSampleTableColumnDefinition extends ScFilterColumnDefinition {
  key: keyof ScSampleTableDisplayRow;
  width: number;
  render?: (row: Partial<ScSampleTableDisplayRow>) => string;
}

export const SC_SAMPLE_TABLE_COLUMNS: ScSampleTableColumnDefinition[] = [
  {
    key: "defect_id",
    title: "Defect ID",
    width: 130,
    filter: "set",
    render: (row) => String(Number(row.defect_id)),
  },
  { key: "images", title: "Images", width: 110, filter: "range" },
  { key: "test_id", title: "Test ID", width: 120, filter: "set" },
  { key: "index_x", title: "Index X", width: 120, filter: "range" },
  { key: "index_y", title: "Index Y", width: 120, filter: "range" },
  { key: "wafer_x", title: "Wafer X", width: 120, filter: "range" },
  { key: "wafer_y", title: "Wafer Y", width: 120, filter: "range" },
  { key: "die_x", title: "Die X", width: 120, filter: "range" },
  { key: "die_y", title: "Die Y", width: 120, filter: "range" },
  { key: "size_x", title: "Size X", width: 120, filter: "range" },
  { key: "size_y", title: "Size Y", width: 120, filter: "range" },
  { key: "size_d", title: "Size D", width: 120, filter: "range" },
  { key: "area", title: "Area", width: 120, filter: "range" },
  { key: "class_number", title: "Class", width: 120, filter: "set" },
  { key: "rough_bin", title: "Rough Bin", width: 120, filter: "set" },
  { key: "final_bin", title: "Final Bin", width: 120, filter: "set" },
  { key: "manual_bin", title: "Manual Bin", width: 120, filter: "set" },
  { key: "adder", title: "Adder", width: 120, filter: "set" },
  { key: "cluster_id", title: "Cluster ID", width: 120, filter: "set" },
  {
    key: "kill_ratio",
    title: "Kill Ratio",
    width: 120,
    filter: "range",
    render: (row) => (row.kill_ratio != null ? row.kill_ratio.toFixed(3) : "-"),
  },
];

export const SC_RECLASSIFY_TABLE_COLUMNS: ScSampleTableColumnDefinition[] = [
  { key: "annotation_label", title: "Annotation", width: 140, filter: "set" },
  { key: "prediction_label", title: "Prediction", width: 140, filter: "set" },
  {
    key: "prediction_confidence",
    title: "Confidence",
    width: 130,
    filter: "range",
    render: (row) =>
      row.prediction_confidence != null ? row.prediction_confidence.toFixed(3) : "-",
  },
];

export const SC_FINAL_CLASS_FILTER_COLUMN: ScFilterColumnDefinition = {
  key: "final_class",
  title: "Final Class",
  filter: "set",
};

export function scSampleTableColumns(
  showReclassifyColumns: boolean,
): ScSampleTableColumnDefinition[] {
  return showReclassifyColumns
    ? [...SC_SAMPLE_TABLE_COLUMNS, ...SC_RECLASSIFY_TABLE_COLUMNS]
    : SC_SAMPLE_TABLE_COLUMNS;
}

export function scGlobalFilterColumns(showReclassifyColumns: boolean): ScFilterColumnDefinition[] {
  const columns = scSampleTableColumns(showReclassifyColumns);
  return showReclassifyColumns ? [...columns, SC_FINAL_CLASS_FILTER_COLUMN] : columns;
}
