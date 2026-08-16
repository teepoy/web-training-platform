import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type {
  ScSampleTableDataSource,
  ScSampleTableDisplayRow,
} from "@/features/sc/domain/workbenchInteraction";

const CSV_EXPORT_BATCH_ROWS = 10_000;
const UTF8_BOM = "\uFEFF";

export interface SampleTableCsvColumn {
  key: string;
  title: string;
}

export interface SampleTableCsvProgress {
  completed: number;
  total: number;
}

export interface ExportSampleTableCsvOptions {
  dataSource: ScSampleTableDataSource;
  columns: readonly SampleTableCsvColumn[];
  defectIds: readonly string[];
  filter: ScSampleTableFilter;
  sort: ScSampleTableSort;
  signal?: AbortSignal;
  batchRows?: number;
  onProgress?: (progress: SampleTableCsvProgress) => void;
}

function csvScalar(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "bigint") return value.toString();
  if (value instanceof Uint8Array) return `[${value.byteLength} bytes]`;
  if (typeof value === "object") {
    return JSON.stringify(value, (_key, item: unknown) =>
      typeof item === "bigint" ? item.toString() : item,
    );
  }
  return String(value);
}

function spreadsheetSafe(value: string, original: unknown): string {
  if (typeof original !== "string" || !/^[=+\-@\t\r]/.test(value)) return value;
  return `'${value}`;
}

export function csvCell(value: unknown): string {
  const text = spreadsheetSafe(csvScalar(value), value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function serializeSampleTableCsvRows(
  columns: readonly SampleTableCsvColumn[],
  rows: readonly ScSampleTableDisplayRow[],
  includeHeader: boolean,
): string {
  const lines: string[] = [];
  if (includeHeader) lines.push(columns.map((column) => csvCell(column.title)).join(","));
  for (const row of rows) {
    lines.push(columns.map((column) => csvCell(Reflect.get(row, column.key))).join(","));
  }
  return lines.length > 0 ? `${lines.join("\r\n")}\r\n` : "";
}

function throwIfAborted(signal: AbortSignal | undefined): void {
  if (signal?.aborted) throw new DOMException("CSV export was cancelled", "AbortError");
}

async function yieldToBrowser(): Promise<void> {
  await new Promise<void>((resolve) => setTimeout(resolve, 0));
}

export async function exportSampleTableCsv(
  options: ExportSampleTableCsvOptions,
): Promise<{ blob: Blob; total: number }> {
  const chunks: BlobPart[] = [UTF8_BOM];
  const seenAnchors = new Set<string>();
  const limit = options.batchRows ?? CSV_EXPORT_BATCH_ROWS;
  let anchor = "0";
  let completed = 0;
  let expectedTotal: number | null = null;
  let includeHeader = true;

  while (true) {
    throwIfAborted(options.signal);
    if (seenAnchors.has(anchor)) throw new Error("Sample export cursor repeated; retry the export");
    seenAnchors.add(anchor);

    const page = await options.dataSource.loadRows({
      defectIds: [...options.defectIds],
      anchor,
      limit,
      filter: options.filter,
      sort: options.sort,
      signal: options.signal,
    });
    throwIfAborted(options.signal);

    if (expectedTotal === null) expectedTotal = page.total;
    else if (page.total !== expectedTotal) {
      throw new Error("Sample data changed during export; retry to create a consistent CSV");
    }

    chunks.push(serializeSampleTableCsvRows(options.columns, page.items, includeHeader));
    includeHeader = false;
    completed += page.items.length;
    options.onProgress?.({ completed, total: expectedTotal });

    if (page.nextAnchor === null) break;
    if (page.items.length === 0)
      throw new Error("Sample export made no progress; retry the export");
    anchor = page.nextAnchor;
    await yieldToBrowser();
  }

  return {
    blob: new Blob(chunks, { type: "text/csv;charset=utf-8" }),
    total: expectedTotal ?? 0,
  };
}

export function sampleTableCsvFileName(value: string): string {
  const base = value
    .trim()
    .replace(/[^a-zA-Z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 160);
  return `${base || "sc-sample-data"}.csv`;
}

export function downloadSampleTableCsv(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = sampleTableCsvFileName(fileName);
  link.click();
  URL.revokeObjectURL(url);
}
