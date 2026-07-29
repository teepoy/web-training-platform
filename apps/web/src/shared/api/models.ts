import { listModelsApiV1ModelsGet } from "@/generated/orval/endpoints/api";
import type { ModelResponse } from "@/generated/orval/models";

export async function listModels(): Promise<ModelResponse[]> {
  const models: ModelResponse[] = [];
  const pageSize = 200;
  let offset = 0;
  while (true) {
    const response = await listModelsApiV1ModelsGet({ offset, limit: pageSize });
    const page = response;
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
