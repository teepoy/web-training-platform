import type { Dataset } from "@/generated/orval/models/dataset";

export const defaultDataset: Dataset = {
  id: "00000000-0000-0000-0000-000000000001",
  name: "test-dataset",
  dataset_type: "classification",
  view_types: ["image_input_v1"],
  org_id: "00000000-0000-0000-0000-000000000000",
  org_name: "Test Org",
  is_public: false,
  created_at: "2025-01-01T00:00:00Z",
  storage_mode: "db_full",
};

export function makeDataset(overrides?: Partial<Dataset>): Dataset {
  return { ...defaultDataset, ...overrides };
}

export function makeDatasets(
  count: number,
  overrides?: (index: number) => Partial<Dataset>,
): Dataset[] {
  return Array.from({ length: count }, (_, i) => {
    const base: Dataset = {
      ...defaultDataset,
      id: `00000000-0000-0000-0000-${String(i + 1).padStart(12, "0")}`,
      name: `test-dataset-${i + 1}`,
    };
    return overrides ? { ...base, ...overrides(i) } : base;
  });
}
