import { req } from "@/shared/api/client";

export function defaultDefectIds(total: number): number[] {
  const count = Math.max(0, Math.floor(total));
  return Array.from({ length: count }, (_, index) => index + 1);
}

export function decodeInt32DefectIds(buffer: ArrayBuffer): number[] {
  if (buffer.byteLength % 4 !== 0) {
    throw new Error("Invalid defect id payload length");
  }
  const view = new DataView(buffer);
  const ids: number[] = [];
  for (let offset = 0; offset < buffer.byteLength; offset += 4) {
    ids.push(view.getInt32(offset, true));
  }
  return ids;
}

async function fetchBinaryDefectIds(path: string): Promise<number[]> {
  const response = await req<Response>(path, {
    headers: { Accept: "application/octet-stream" },
  });
  return decodeInt32DefectIds(await response.arrayBuffer());
}

export function fetchInspectionDefectIds(
  inspectionTime: string,
  waferKey: number,
): Promise<number[]> {
  return fetchBinaryDefectIds(
    `/sc/inspections/${encodeURIComponent(inspectionTime)}/${encodeURIComponent(waferKey)}/defect-ids.bin`,
  );
}

export function fetchDatasetDefectIds(datasetId: string): Promise<number[]> {
  return fetchBinaryDefectIds(
    `/sc/datasets/${encodeURIComponent(datasetId)}/defect-ids.bin`,
  );
}
