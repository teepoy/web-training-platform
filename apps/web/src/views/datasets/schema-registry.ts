import { type Component, defineAsyncComponent } from "vue";

export interface DatasetSchemaDescriptor {
  /** Backend dataset_type string, e.g. "image_classification". */
  datasetType: string;
  /** Backend task_type string, e.g. "classification". */
  taskType: string;
  /** High-level annotation shape. */
  annotationType: "choice" | "boxes" | "text" | "none";
  /** Async component factory for the dataset list shim. */
  shimComponent: Component;
  /**
   * Generates a deterministic synthetic sample item.
   * Same factory is reused in Storybook stories and e2e fixtures.
   */
  mockSampleFactory: (index: number, labelSpace?: string[]) => unknown;
}

const _registry = new Map<string, DatasetSchemaDescriptor>();

export function registerDatasetSchema(schema: DatasetSchemaDescriptor): void {
  _registry.set(schema.datasetType, schema);
}

export function getDatasetSchema(datasetType: string): DatasetSchemaDescriptor | undefined {
  return _registry.get(datasetType);
}

/**
 * Resolve the dataset list shim component for a dataset type.
 * Falls back to the classification shim for unknown types.
 */
export function resolveDatasetShim(datasetType: string | null | undefined): Component {
  const schema = _registry.get(datasetType ?? "");
  if (schema) return schema.shimComponent;
  // Fallback for unknown types: classification shim
  const fallback = _registry.get("image_classification");
  return (
    fallback?.shimComponent ??
    defineAsyncComponent(() => import("../shims/ClassificationDatasetsShim.vue"))
  );
}

export function getMockSampleFactory(
  datasetType: string,
): ((index: number, labelSpace?: string[]) => unknown) | undefined {
  return _registry.get(datasetType)?.mockSampleFactory;
}

export function listRegisteredDatasetTypes(): string[] {
  return [..._registry.keys()];
}
