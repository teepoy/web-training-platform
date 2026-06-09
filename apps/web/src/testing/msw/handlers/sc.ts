import { http, HttpResponse } from "msw";
import { create, toBinary } from "@bufbuild/protobuf";
import {
  ClassListSchema,
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

export function makeFakeClassListBytes(sampleCount: number): Uint8Array {
  const classNumbers: Record<string, { count: number; defectIds: number[] }> = {};
  const roughBins: Record<string, { count: number; defectIds: number[] }> = {};
  for (let i = 0; i < sampleCount; i += 1) {
    const defectId = i + 1;
    const classKey = String(i % 3);
    const binKey = String(i % 5);
    classNumbers[classKey] ??= { count: 0, defectIds: [] };
    roughBins[binKey] ??= { count: 0, defectIds: [] };
    classNumbers[classKey].count += 1;
    roughBins[binKey].count += 1;
    classNumbers[classKey].defectIds.push(defectId);
    roughBins[binKey].defectIds.push(defectId);
  }
  const msg = create(ClassListSchema, { classNumbers, roughBins });
  return toBinary(ClassListSchema, msg);
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

export const scClassListHandler = http.get(
  "/api/v1/sc/datasets/:datasetId/class-list",
  () => {
    const bytes = makeFakeClassListBytes(1000);
    return new HttpResponse(bytes, {
      status: 200,
      headers: {
        "Content-Type": "application/x-protobuf",
      },
    });
  },
);

export const scHandlers = [scPlotPointsHandler, scClassListHandler];
