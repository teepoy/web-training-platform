# Datasets Shim Architecture

The `DatasetsView` uses a shim-based architecture to support different UI layouts and behaviors based on the task type of the datasets being displayed. This allows the platform to provide specialized views for different task types (e.g., Classification vs. VQA) while sharing common data fetching and state management logic.

## Overview

The architecture consists of four main parts:

1.  **Host (`DatasetsView.vue`)**: A thin container that manages data fetching and determines which specialized "shim" to render.
2.  **Registry (`registry.ts`)**: A central map that associates task types with their corresponding shim components.
3.  **Adapter (`useDatasetsAdapter.ts`)**: A composable that centralizes data normalization, permissions, and common UI properties (like table columns and toolbar plugins).
4.  **Shims (`shims/*.vue`)**: Specialized components that render the actual UI for a specific task type.

## How it Works

### 1. Host: `DatasetsView.vue`

The host component is responsible for:
- Fetching the list of datasets using Vue Query.
- Initializing the `useDatasetsAdapter` with the fetched data and event handlers.
- Determining the `activeTaskType` (currently based on the first dataset in the list).
- Resolving the `activeShim` component via the registry.
- Rendering the `DatasetPageShell` and the resolved shim.

### 2. Registry: `registry.ts`

The registry defines the mapping between `TaskType` and shim components:

```typescript
export const DATASET_SHIM_REGISTRY = {
  classification: defineAsyncComponent(() => import("./shims/ClassificationDatasetsShim.vue")),
  vqa: defineAsyncComponent(() => import("./shims/VqaDatasetsShim.vue")),
} satisfies Record<TaskType, Component>;
```

The `resolveDatasetShim` function provides the resolution logic, including fallback behavior:
- If `taskType` is `vqa`, it returns the VQA shim.
- Otherwise, it falls back to the `classification` shim.

### 3. Adapter: `useDatasetsAdapter.ts`

The adapter provides a unified interface for shims to access:
- **Normalized Data**: Datasets with consistent field types.
- **Permissions**: `isSuperadmin`, `canDelete`, etc.
- **UI Props**: Pre-configured `columns` for `DatasetTable` and `importerPlugins` for `DatasetToolbar`.
- **Event Handlers**: Wrapped handlers for viewing, deleting, and toggling public status.

### 4. Shims

Shims are the "leaf" components that define the layout. They typically use shared components like `DatasetToolbar` and `DatasetTable`.

- **`ClassificationDatasetsShim.vue`**: The default view for classification tasks.
- **`VqaDatasetsShim.vue`**: A specialized view for Visual Question Answering, which can include additional alerts or custom columns.

## Extension Flow: Adding a New Shim

To add support for a new task type (e.g., `object-detection`):

1.  **Create the Shim**:
    Create `apps/web/src/views/datasets/shims/ObjectDetectionDatasetsShim.vue`. You can copy `ClassificationDatasetsShim.vue` as a starting point.
    
2.  **Register the Shim**:
    Update `apps/web/src/views/datasets/registry.ts`:
    ```typescript
    export const DATASET_SHIM_REGISTRY = {
      classification: ...,
      vqa: ...,
      "object-detection": defineAsyncComponent(() => import("./shims/ObjectDetectionDatasetsShim.vue")),
    };
    ```

3.  **Update Resolution Logic**:
    Update `resolveDatasetShim` in `registry.ts` to handle the new type:
    ```typescript
    export function resolveDatasetShim(taskType: TaskType | undefined): Component {
      if (taskType === "vqa") return DATASET_SHIM_REGISTRY.vqa;
      if (taskType === "object-detection") return DATASET_SHIM_REGISTRY["object-detection"];
      return DATASET_SHIM_REGISTRY.classification;
    }
    ```

## Fallback Behavior

If a task type is not explicitly handled in `resolveDatasetShim`, the system defaults to the `classification` shim. This ensures that the datasets list remains functional even as new task types are introduced to the backend before specialized frontend shims are implemented.
