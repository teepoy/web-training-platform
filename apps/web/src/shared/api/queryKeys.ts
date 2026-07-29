import type { QueryKey } from "@tanstack/vue-query";

export function orgScopedQueryKey(orgId: string | null | undefined, queryKey: QueryKey): QueryKey {
  return ["org", orgId ?? "none", ...queryKey];
}

export const queryKeys = {
  org: orgScopedQueryKey,
} as const;
