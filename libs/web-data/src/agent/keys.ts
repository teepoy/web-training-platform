export const agentKeys = {
  all: ["agent"] as const,
  surface: (sessionId: string, surfaceId: string) =>
    ["agent", "surface", sessionId, surfaceId] as const,
  query: (datasetId: string, queryType: string) =>
    ["agent", "query", datasetId, queryType] as const,
};
