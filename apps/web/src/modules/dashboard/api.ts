import { req } from "@/shared/api";
import type { DashboardResponse } from "./types";

export function getDashboard(): Promise<DashboardResponse> {
  return req<DashboardResponse>("/dashboard");
}
