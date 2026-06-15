import {
  deleteModelApiV1ModelsModelIdDelete,
  listModelsApiV1ModelsGet,
} from "@/generated/orval/endpoints/api";
import type { ModelResponse } from "@/generated/orval/models";
import { req } from "./client";

export async function listModels(): Promise<ModelResponse[]> {
  const response = await listModelsApiV1ModelsGet();
  return response.data as ModelResponse[];
}

export async function renameModel(
  modelId: string,
  name: string,
): Promise<ModelResponse> {
  return req<ModelResponse>(`/models/${encodeURIComponent(modelId)}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export async function deleteModel(modelId: string): Promise<void> {
  await deleteModelApiV1ModelsModelIdDelete(modelId);
}
