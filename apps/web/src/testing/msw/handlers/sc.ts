import { http, HttpResponse } from "msw";
import { create, toBinary } from "@bufbuild/protobuf";
import { WaferMapResponseSchema } from "@/features/sc/generated/proto/sc/v1/sample_pb";

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

export const scPlotPointsStreamHandler = http.get(
  "/api/v1/sc/datasets/:datasetId/plot-points/stream",
  () =>
    new HttpResponse(
      [
        'event: progress\ndata: {"event_type":"progress","operation":"sc.plot-points","status":"loading","message":"Preparing plot points"}\n\n',
        'event: done\ndata: {"event_type":"done"}\n\n',
      ].join(""),
      {
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
        },
      },
    ),
);

export const scHandlers = [scPlotPointsStreamHandler, scPlotPointsHandler];
