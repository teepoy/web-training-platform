export const datasetKeys = {
  all: ["datasets"] as const,
  list: (orgId?: string | null) => ["datasets", "list", orgId ?? ""] as const,
  detail: (id: string) => ["datasets", "detail", id] as const,
  annotationStats: (id: string) => ["datasets", "annotation-stats", id] as const,
};
