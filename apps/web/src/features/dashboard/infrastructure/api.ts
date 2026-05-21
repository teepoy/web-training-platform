import { req } from "@/shared/api";
import type { DashboardResponse } from '../domain/models';

export function getDashboard(): Promise<DashboardResponse> {
  return req<DashboardResponse>("/dashboard");
}
