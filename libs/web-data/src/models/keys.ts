export const modelKeys = {
  all: ["models"] as const,
  list: (datasetId?: string, jobId?: string) =>
    ["models", "list", datasetId ?? "", jobId ?? ""] as const,
  detail: (id: string) => ["models", "detail", id] as const,
};

export const presetKeys = {
  all: ["presets"] as const,
  list: [] as const,
  detail: (id: string) => ["presets", "detail", id] as const,
};

export const scheduleKeys = {
  all: ["schedules"] as const,
  list: [] as const,
  detail: (id: string) => ["schedules", "detail", id] as const,
  runs: (id: string) => ["schedules", "runs", id] as const,
};
