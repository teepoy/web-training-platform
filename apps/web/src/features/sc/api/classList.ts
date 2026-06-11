import { fromBinary } from "@bufbuild/protobuf";
import { req } from "@/shared/api/client";
import {
  ClassListSchema,
  type ClassList,
} from "../generated/proto/sc/v1/sample_pb";
import {
  appendScMapFilterParams,
  type ScMapFilter,
} from "./plotPoints";

async function decodeClassList(path: string): Promise<ClassList> {
  const response = await req<Response>(path, {
    headers: { Accept: "application/x-protobuf" },
  });
  return fromBinary(
    ClassListSchema,
    new Uint8Array(await response.arrayBuffer()),
  );
}

function classListParams(
  filter?: ScMapFilter,
  legendGroupBy?: string,
): string {
  const params = new URLSearchParams();
  appendScMapFilterParams(params, filter);
  if (legendGroupBy) params.set("legend_group_by", legendGroupBy);
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function fetchScDatasetClassList(
  datasetId: string,
  filter?: ScMapFilter,
  legendGroupBy?: string,
): Promise<ClassList> {
  return decodeClassList(
    `/sc/datasets/${encodeURIComponent(datasetId)}/class-list${classListParams(filter, legendGroupBy)}`,
  );
}

export function fetchScInspectionClassList(
  inspectionTime: string,
  waferKey: number,
  filter?: ScMapFilter,
  legendGroupBy?: string,
): Promise<ClassList> {
  return decodeClassList(
    `/sc/inspections/${encodeURIComponent(inspectionTime)}/${waferKey}/class-list${classListParams(filter, legendGroupBy)}`,
  );
}
