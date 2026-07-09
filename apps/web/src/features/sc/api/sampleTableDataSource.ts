import { streamApiSse } from "@/shared/api/sse";
import {
  buildScSampleTableRowsRequest,
  type ScSampleTableDataSource,
  type ScSampleTableRowsPage,
  type ScSampleTableRowsQuery,
} from "@/features/sc/domain/workbenchInteraction";
import type { ScSampleTableRowsResponse } from "@/generated/orval/models/scSampleTableRowsResponse";

function normalizeRowsResponse(response: ScSampleTableRowsResponse): ScSampleTableRowsPage {
  return {
    items: response.items,
    total: response.total,
    nextAnchor: response.next_anchor ?? null,
  };
}

export function createInspectionSampleTableDataSource(
  inspectionTime: string,
  waferKey: number,
  onProgress?: (message: string) => void,
): ScSampleTableDataSource {
  return {
    scopeKey: `inspection:${inspectionTime}:${waferKey}`,
    async loadRows(query: ScSampleTableRowsQuery): Promise<ScSampleTableRowsPage> {
      const dataEvent = await streamApiSse(
        `/sc/inspections/${encodeURIComponent(inspectionTime)}/${encodeURIComponent(waferKey)}/sample-table-rows/stream`,
        {
          method: "POST",
          body: buildScSampleTableRowsRequest(query),
          onEvent: (event) => {
            if (event.event_type === "progress") {
              onProgress?.(event.message || event.status || "Loading rows...");
            }
          },
        },
      );
      const data = dataEvent?.payload;
      if (!data || !("items" in data)) {
        throw new Error("Invalid sample table response");
      }
      // ts-ignore-next-line
      return normalizeRowsResponse(data as unknown as ScSampleTableRowsResponse); // ast-grep-ignore: forbid-unsafe-type-casts
    },
  };
}
