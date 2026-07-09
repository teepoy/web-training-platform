import { describe, expect, it, vi } from "vitest";
import { decodeInt32DefectIds, fetchInspectionDefectIds } from "../defectIds";
import { req } from "@/shared/api/client";

vi.mock("@/shared/api/client", () => ({
  req: vi.fn(),
}));

function int32Buffer(values: number[]): ArrayBuffer {
  const buffer = new ArrayBuffer(values.length * 4);
  const view = new DataView(buffer);
  values.forEach((value, index) => view.setInt32(index * 4, value, true));
  return buffer;
}

describe("SC defect id binary helpers", () => {
  it("decodes little-endian Int32 defect ids", () => {
    expect(decodeInt32DefectIds(int32Buffer([1, 2, 10]))).toEqual([1, 2, 10]);
  });

  it("rejects invalid binary payload lengths", () => {
    expect(() => decodeInt32DefectIds(new ArrayBuffer(3))).toThrow(
      "Invalid defect id payload length",
    );
  });

  it("fetches the inspection binary endpoint", async () => {
    vi.mocked(req).mockResolvedValueOnce(new Response(int32Buffer([3])));

    await expect(fetchInspectionDefectIds("2026-01-01 00:00:00", 2)).resolves.toEqual([3]);

    expect(req).toHaveBeenNthCalledWith(
      1,
      "/sc/inspections/2026-01-01%2000%3A00%3A00/2/defect-ids.bin",
      { headers: { Accept: "application/octet-stream" } },
    );
  });
});
