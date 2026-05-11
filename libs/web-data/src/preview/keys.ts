export const previewKeys = {
  all: ["preview"] as const,
  session: (sessionId: string) => [...previewKeys.all, "session", sessionId] as const,
  items: (sessionId: string, cursor: string | null, limit: number) =>
    [...previewKeys.all, "items", sessionId, { cursor, limit }] as const,
  persistStatus: (sessionId: string) =>
    [...previewKeys.all, "persist-status", sessionId] as const,
};
