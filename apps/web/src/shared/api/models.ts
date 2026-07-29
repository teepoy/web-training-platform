import {
  deleteModelApiV1ModelsModelIdDelete,
  listModelsApiV1ModelsGet,
} from "@/generated/orval/endpoints/api";
import type { ModelResponse } from "@/generated/orval/models";
import { req } from "./client";

export async function listModels(): Promise<ModelResponse[]> {
  const models: ModelResponse[] = [];
  const pageSize = 200;
  let offset = 0;
  while (true) {
    const response = await listModelsApiV1ModelsGet({ offset, limit: pageSize });
    const page = response.data;
    if (!("items" in page)) {
      throw new Error("Failed to list models");
    }
    models.push(...page.items);
    if (models.length >= page.total) {
      return models;
    }
    if (page.items.length === 0) {
      throw new Error("Model pagination returned an incomplete empty page");
    }
    offset += page.items.length;
  }
}

export async function renameModel(modelId: string, name: string): Promise<ModelResponse> {
  return req<ModelResponse>(`/models/${encodeURIComponent(modelId)}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export async function deleteModel(modelId: string): Promise<void> {
  await deleteModelApiV1ModelsModelIdDelete(modelId);
}
