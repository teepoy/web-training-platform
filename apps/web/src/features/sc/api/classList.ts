import { fromBinary } from "@bufbuild/protobuf";
import { req } from "@/shared/api/client";
import {
  ClassListSchema,
  type ClassList,
} from "../generated/proto/sc/v1/sample_pb";

async function decodeClassList(path: string): Promise<ClassList> {
  const response = await req<Response>(path, {
    headers: { Accept: "application/x-protobuf" },
  });
  return fromBinary(
    ClassListSchema,
    new Uint8Array(await response.arrayBuffer()),
  );
}

export function fetchScDatasetClassList(datasetId: string): Promise<ClassList> {
  return decodeClassList(
    `/sc/datasets/${encodeURIComponent(datasetId)}/class-list`,
  );
}

export function fetchScInspectionClassList(
  inspectionTime: string,
  waferKey: number,
): Promise<ClassList> {
  return decodeClassList(
    `/sc/inspections/${encodeURIComponent(inspectionTime)}/${waferKey}/class-list`,
  );
}
