import { req } from "@/shared/api/client";
import type { Model } from "@/types";

export function listModels(): Promise<Model[]> {
  return req<Model[]>("/models");
}
