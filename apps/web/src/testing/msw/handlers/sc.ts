import { http, HttpResponse } from "msw";
import { create, toBinary } from "@bufbuild/protobuf";
import {
  WaferMapResponseSchema,
} from "@/features/sc/generated/proto/sc/v1/sample_pb";

function makeFakePoints(sampleCount: number): number[] {
  return Array.from({ length: sampleCount * 6 }, (_, i) => i % 100);
}

export function makeFakePlotPointsBytes(sampleCount: number): Uint8Array {
  const pts = makeFakePoints(sampleCount);
  const msg = create(WaferMapResponseSchema, {
    total: sampleCount,
    waferPoints: pts,
    diePoints: pts,
  });
  return toBinary(WaferMapResponseSchema, msg);
}

export const scPlotPointsHandler = http.get(
  "/api/v1/sc/datasets/:datasetId/plot-points",
  ({ params }) => {
    const sampleCount = 1000;
    const bytes = makeFakePlotPointsBytes(sampleCount);
    return new HttpResponse(bytes, {
      status: 200,
      headers: {
        "Content-Type": "application/x-protobuf",
      },
    });
  },
);

export const scSampleTableRowsHandler = http.post(
  "/api/v1/sc/inspections/:inspectionTime/:waferKey/sample-table-rows",
  async ({ request }) => {
    const body = (await request.json()) as {
      defect_ids?: string[];
      page?: number;
      page_size?: number;
      filter?: Record<
        string,
        | { operator: "in"; values: Array<string | number> }
        | { operator: "between"; min: number; max: number }
      >;
      sort?: { field?: string; direction?: string };
    };
    const allItems = Array.from({ length: 200 }, (_, i) => {
      const defectId = i + 1;
      return {
        defect_id: String(defectId),
        rough_bin: defectId % 5,
        class_number: defectId % 3,
        test_id: defectId % 100,
        wafer_x: 150_000_000 + defectId * 1000,
        wafer_y: 150_000_000 + defectId * 1000,
        index_x: defectId % 37,
        index_y: defectId % 60,
        adder: 0,
        cluster_id: defectId % 10,
        die_x: defectId % 37,
        die_y: defectId % 60,
        size_x: 50 + (defectId % 450),
        size_y: 50 + (defectId % 450),
        size_d: Math.round(Math.sqrt(2) * (50 + (defectId % 450))),
        area: (50 + (defectId % 450)) ** 2,
        final_bin: defectId % 256,
        manual_bin: defectId % 256,
        kill_ratio: parseFloat(((defectId % 100) / 100).toFixed(3)),
      };
    });
    const requested = new Set(body.defect_ids ?? []);
    let items =
      requested.size > 0
        ? allItems.filter((item) => requested.has(item.defect_id))
        : allItems;

    for (const [field, filter] of Object.entries(body.filter ?? {})) {
      items = items.filter((item) => {
        const value = item[field as keyof typeof item];
        if (filter.operator === "in") {
          return filter.values.some(
            (candidate) => String(candidate) === String(value),
          );
        }
        return (
          typeof value === "number" &&
          value >= filter.min &&
          value <= filter.max
        );
      });
    }

    const sort = body.sort;
    if (
      sort?.field &&
      (sort.direction === "asc" || sort.direction === "desc")
    ) {
      items = [...items].sort((left, right) => {
        const leftValue = left[sort.field as keyof typeof left];
        const rightValue = right[sort.field as keyof typeof right];
        if (leftValue === rightValue) return 0;
        const direction = sort.direction === "desc" ? -1 : 1;
        return (leftValue < rightValue ? -1 : 1) * direction;
      });
    }

    const total = items.length;
    const pageSize = body.page_size ?? 1000;
    const page = body.page ?? 0;
    items = items.slice(page * pageSize, (page + 1) * pageSize);
    return HttpResponse.json({ items, total }, { status: 200 });
  },
);

export const scHandlers = [
  scPlotPointsHandler,
  scSampleTableRowsHandler,
];
