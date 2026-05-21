import { req } from "./client";
import type { Organization } from "./types";

export function fetchOrganizations(): Promise<Organization[]> {
  return req<Organization[]>("/organizations");
}
