export const taskTrackerKeys = {
  all: ["task-tracker"] as const,
  list: (kind?: string) => ["task-tracker", "list", kind ?? "all"] as const,
  detail: (id: string) => ["task-tracker", "detail", id] as const,
};
