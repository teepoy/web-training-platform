import { tableFromIPC } from "apache-arrow";
import type { Table } from "apache-arrow";

export type ArrowBackedRow = Record<string, unknown>;

export interface ArrowBackedRowsStats {
  length: number;
  hydratedRows: number;
  rowObjectsCreated: number;
}

interface ArrowPage {
  start: number;
  end: number;
  table: Table;
}

const ROW_INDEX = Symbol("arrow-row-index");
type InternalArrowRow = ArrowBackedRow & { [ROW_INDEX]: number };
const ARROW_FIELDS = [
  "defect_id",
  "rough_bin",
  "class_number",
  "images",
  "test_id",
  "wafer_x",
  "wafer_y",
  "index_x",
  "index_y",
  "adder",
  "cluster_id",
  "die_x",
  "die_y",
  "reticle_x",
  "reticle_y",
  "size_x",
  "size_y",
  "size_d",
  "area",
  "final_bin",
  "manual_bin",
  "kill_ratio",
  "annotation_label",
  "prediction_label",
  "prediction_confidence",
] as const;

function normalizeArrowValue(value: unknown): unknown {
  if (typeof value === "bigint") return Number(value);
  if (value && typeof value === "object" && "toJSON" in value) {
    return (value as { toJSON: () => unknown }).toJSON();
  }
  return value;
}

function numericIndex(property: PropertyKey): number | null {
  if (typeof property !== "string" || !/^(0|[1-9]\d*)$/.test(property)) return null;
  const index = Number(property);
  return Number.isSafeInteger(index) ? index : null;
}

export class ArrowBackedRows {
  readonly rows: ArrowBackedRow[];

  private defectIds: Table | null = null;
  private defectIdField = "defect_id";
  private pages: ArrowPage[] = [];
  private rowCache = new Map<number, ArrowBackedRow>();
  private rowPrototype: ArrowBackedRow;
  private total = 0;

  constructor() {
    const owner = this;
    this.rowPrototype = {};
    Object.defineProperty(this.rowPrototype, "_isHydrated", {
      get(this: ArrowBackedRow) {
        return owner.findPage((this as InternalArrowRow)[ROW_INDEX]) !== undefined;
      },
    });
    for (const field of ARROW_FIELDS) {
      Object.defineProperty(this.rowPrototype, field, {
        get(this: ArrowBackedRow) {
          const index = (this as InternalArrowRow)[ROW_INDEX];
          return field === "defect_id"
            ? owner.getDefectId(index)
            : owner.getPageValue(index, field);
        },
      });
    }

    const arrayTarget: ArrowBackedRow[] = [];
    let rowsProxy: ArrowBackedRow[];
    rowsProxy = new Proxy(arrayTarget, {
      get: (target, property, receiver) => {
        if (property === "length") return this.total;
        if (property === "slice") {
          return (start = 0, end = this.total) => {
            if (start === 0 && end >= this.total) return rowsProxy;
            const safeStart = Math.max(0, start);
            const safeEnd = Math.min(end, this.total);
            return Array.from({ length: Math.max(0, safeEnd - safeStart) }, (_, offset) =>
              this.getRow(safeStart + offset),
            );
          };
        }
        const index = numericIndex(property);
        if (index !== null) return index < this.total ? this.getRow(index) : undefined;
        return Reflect.get(target, property, receiver);
      },
      has: (target, property) => {
        const index = numericIndex(property);
        return index !== null ? index < this.total : Reflect.has(target, property);
      },
    });
    this.rows = rowsProxy;
  }

  reset(total: number, defectIdIpc: unknown, defectIdField = "defect_id"): void {
    this.total = total;
    this.defectIds = tableFromIPC(defectIdIpc as Uint8Array);
    this.defectIdField = defectIdField;
    this.pages = [];
    this.rowCache.clear();
  }

  resetWithoutDefectIds(total: number): void {
    this.total = total;
    this.defectIds = null;
    this.defectIdField = "defect_id";
    this.pages = [];
    this.rowCache.clear();
  }

  hydrate(start: number, ipc: unknown): ArrowBackedRow[] {
    const table = tableFromIPC(ipc as Uint8Array);
    const end = Math.min(this.total, start + table.numRows);
    this.pages = this.pages.filter((page) => page.end <= start || page.start >= end);
    this.pages.push({ start, end, table });
    this.pages.sort((left, right) => left.start - right.start);
    return Array.from({ length: end - start }, (_, offset) => this.getRow(start + offset));
  }

  retainRange(start: number, end: number): void {
    this.pages = this.pages.filter((page) => page.start >= start && page.end <= end);
    for (const index of this.rowCache.keys()) {
      if (index < start || index >= end) this.rowCache.delete(index);
    }
  }

  clear(): void {
    this.total = 0;
    this.defectIds = null;
    this.pages = [];
    this.rowCache.clear();
  }

  getStats(): ArrowBackedRowsStats {
    return {
      length: this.total,
      hydratedRows: this.pages.reduce((sum, page) => sum + page.end - page.start, 0),
      rowObjectsCreated: this.rowCache.size,
    };
  }

  getAllDefectIds(): number[] {
    const column = this.defectIds?.getChild(this.defectIdField);
    if (!column) return [];
    const ids: number[] = [];
    for (let index = 0; index < this.total; index += 1) {
      const value = Number(normalizeArrowValue(column.get(index)));
      if (Number.isFinite(value)) ids.push(value);
    }
    return ids;
  }

  private getRow(index: number): ArrowBackedRow {
    const cached = this.rowCache.get(index);
    if (cached) return cached;
    const row = Object.create(this.rowPrototype) as ArrowBackedRow;
    Object.defineProperty(row, ROW_INDEX, { value: index });
    this.rowCache.set(index, row);
    return row;
  }

  private findPage(index: number): ArrowPage | undefined {
    return this.pages.find((page) => index >= page.start && index < page.end);
  }

  private getDefectId(index: number): string {
    const page = this.findPage(index);
    const value =
      this.defectIds?.getChild(this.defectIdField)?.get(index) ??
      page?.table.getChild("defect_id")?.get(index - page.start);
    return value == null || value === "" ? `__row_${index}` : String(normalizeArrowValue(value));
  }

  private getPageValue(index: number, field: string): unknown {
    const page = this.findPage(index);
    if (!page) return undefined;
    return normalizeArrowValue(page.table.getChild(field)?.get(index - page.start));
  }
}
