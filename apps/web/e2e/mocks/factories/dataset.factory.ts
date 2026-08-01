import type { Dataset } from "@/generated/orval/models";

/**
 * Default flower classification dataset matching old e2e
 * `flowerDataset` constant.
 */
export function makeFlowerDataset(overrides?: Partial<Dataset>): Dataset {
  return {
    id: "dataset-e2e-1",
    name: "flowers-dataset",
    dataset_type: "image_classification",
    task_spec: {
      task_type: "classification",
      label_space: ["rose", "tulip"],
    },
    created_at: "2026-01-01T00:00:00Z",
    org_id: "org-e2e-1",
    org_name: "E2E Org",
    is_public: false,
    ...overrides,
  };
}

/**
 * Generic image classification dataset factory.
 */
export function makeImageDataset(overrides?: Partial<Dataset>): Dataset {
  return {
    id: "dataset-img-1",
    name: "image-dataset",
    dataset_type: "image_classification",
    task_spec: {
      task_type: "classification",
      label_space: ["cat", "dog"],
    },
    created_at: "2026-01-01T00:00:00Z",
    org_id: "org-e2e-1",
    org_name: "E2E Org",
    is_public: false,
    ...overrides,
  };
}

/**
 * Minimal anonymous dataset factory — no opinionated defaults.
 */
export function makeDataset(dataset_type: string, overrides?: Partial<Dataset>): Dataset {
  return {
    id: "dataset-new-1",
    name: `${dataset_type}-dataset`,
    dataset_type,
    task_spec: {},
    created_at: "2026-01-01T00:00:00Z",
    org_id: "org-e2e-1",
    org_name: "E2E Org",
    is_public: false,
    ...overrides,
  };
}
