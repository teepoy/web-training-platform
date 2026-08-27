import { type Component, defineAsyncComponent } from "vue";

export interface DatasetSchemaDescriptor {
  /** Backend dataset_type string, e.g. "image_classification". */
  datasetType: string;
  /** Backend task_type string, e.g. "classification". */
  taskType: string;
  /** Supported view types for rendering this dataset. */
  viewTypes?: string[];
  /** High-level annotation shape. */
  annotationType: "choice" | "boxes" | "text" | "none";
  /** Async component factory for the dataset list shim. */
  shimComponent: Component;
  /** Async component factory for per-view rendering (distinct from list shim). */
  viewComponent?: Component;
  /**
   * When true, the view component fetches its own samples and the parent page
   * should NOT call the generic `/datasets/{id}/views/{viewType}/samples` endpoint
   * (which is unsupported for some storage modes such as `file_shard_sparse`).
   */
  selfLoading?: boolean;
}

/** Dataset types → schema descriptor (for list shims, schema info). */
const _datasetRegistry = new Map<string, DatasetSchemaDescriptor>();

/** View types → schema descriptor (first-registration-wins for shared view types). */
const _viewRegistry = new Map<string, DatasetSchemaDescriptor>();

const _classificationFallbackShim = defineAsyncComponent(
  () => import("../dataset-types/classification/views/ListShim.vue"),
);

/**
 * Register a dataset schema descriptor.
 * Dataset types and view types are registered into separate maps
 * so view-type lookups never overwrite dataset-type entries.
 * Shared view types (e.g. image_input_v1) use first-registration-wins.
 */
export function registerDatasetSchema(schema: DatasetSchemaDescriptor): void {
  _datasetRegistry.set(schema.datasetType, schema);
  if (schema.viewTypes) {
    schema.viewTypes.forEach((vt) => {
      if (!_viewRegistry.has(vt)) {
        _viewRegistry.set(vt, schema);
      }
    });
  }
}

/**
 * Look up a schema descriptor by dataset type string.
 */
export function getDatasetSchema(datasetType: string): DatasetSchemaDescriptor | undefined {
  return _datasetRegistry.get(datasetType);
}

/**
 * Look up a schema descriptor by view type string.
 * Returns the parent dataset schema that owns the view type.
 */
export function getViewSchema(viewType: string): DatasetSchemaDescriptor | undefined {
  return _viewRegistry.get(viewType);
}

/**
 * Resolve the dataset list shim component for a dataset type.
 * Falls back to the classification shim for unknown types.
 *
 * For view-type → view rendering resolution, use {@link resolveViewComponent}.
 */
export function resolveDatasetShim(
  datasetType: string | null | undefined,
  viewTypes?: string[] | string,
): Component {
  if (datasetType && _datasetRegistry.has(datasetType)) {
    return _datasetRegistry.get(datasetType)!.shimComponent;
  }

  if (viewTypes) {
    const vtList =
      typeof viewTypes === "string" ? viewTypes.split(",").map((s) => s.trim()) : viewTypes;
    for (const vt of vtList) {
      const schema = _viewRegistry.get(vt);
      if (schema) {
        return schema.shimComponent;
      }
    }
  }

  // Fallback for unknown types: classification shim
  const fallback = _datasetRegistry.get("image_classification");
  return fallback?.shimComponent ?? _classificationFallbackShim;
}

/**
 * Resolve a view-type string to its dedicated per-view rendering component.
 * Returns the viewComponent if registered, otherwise falls back to the
 * parent schema's shimComponent (dataset list shim).
 *
 * This is the primary API for rendering a dataset's samples with a given view type.
 */
export function resolveViewComponent(viewType: string): Component | undefined {
  const schema = _viewRegistry.get(viewType);
  if (!schema) return undefined;
  return schema.viewComponent ?? schema.shimComponent;
}

export function listRegisteredDatasetTypes(): string[] {
  return [..._datasetRegistry.keys()];
}

export function listRegisteredViewTypes(): string[] {
  return [..._viewRegistry.keys()];
}
