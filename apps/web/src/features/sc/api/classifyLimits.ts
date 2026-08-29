import { API_BASE, requestData } from "@/shared/api/client";

export interface ScClassifyLimits {
  max_rows: number;
}

export function getScClassifyLimits(): Promise<ScClassifyLimits> {
  return requestData<ScClassifyLimits>(`${API_BASE}/sc/data/classify-limits`);
}
