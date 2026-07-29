import { tableFromIPC } from "apache-arrow";

export interface DecodedSampleArrowTable {
  columns: Record<string, unknown[]>;
  numRows: number;
}

function normalizeArrowValue(value: unknown): unknown {
  if (typeof value === "bigint") return Number(value);
  if (value && typeof value === "object" && "toJSON" in value) {
    return (value as { toJSON: () => unknown }).toJSON();
  }
  return value;
}

export function decodeSampleArrowIpc(data: ArrayBuffer): DecodedSampleArrowTable {
  const table = tableFromIPC(new Uint8Array(data));
  const columns: Record<string, unknown[]> = {};
  for (const field of table.schema.fields) {
    const vector = table.getChild(field.name);
    columns[field.name] = Array.from({ length: table.numRows }, (_, index) =>
      normalizeArrowValue(vector?.get(index)),
    );
  }
  return { columns, numRows: table.numRows };
}
