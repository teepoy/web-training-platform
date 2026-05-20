# Datasets Shim Architecture

The `DatasetsView` uses a schema-driven shim architecture to support different UI layouts and behaviors based on the **dataset type** of the datasets being displayed. Each dataset type (e.g., `image_classification`, `image_vqa`, `image_detection`) has a corresponding schema descriptor that bundles its shim component, annotation shape, and mock data factory.

## Overview

The architecture consists of five layers:

1. **Host (`DatasetsView.vue`)**: Thin container — fetches data, resolves active dataset type, renders the shim.
2. **App schema barrel (`schemas/`)**: One module per dataset type; each registers itself into the schema registry on import.
3. **Schema registry (`schema-registry.ts`)**: Map of `dataset_type → DatasetSchemaDescriptor`; provides `resolveDatasetShim()`.
4. **Shared UI package (`@platform/web-ui`)**: Reusable Vue/Naive UI components and dataset-list helpers.
5. **Shims (`shims/*.vue`)**: Leaf components defining the per-type dataset list layout.

## How It Works

### 1. Host: `DatasetsView.vue`

The host is responsible for:
- Fetching the dataset list via Vue Query.
- Deriving `activeDatasetType` from `datasets[0].dataset_type` (e.g. `"image_classification"`).
- Calling `resolveDatasetShim(activeDatasetType)` to get the correct shim component.
- Rendering `DatasetPageShell` + the resolved shim.

### 2. Schema Registry: `schema-registry.ts`

```typescript
// apps/web/src/views/datasets/schema-registry.ts

export interface DatasetSchemaDescriptor {
  datasetType: string;          // e.g. "image_classification"
  taskType: string;             // e.g. "classification"
  annotationType: "choice" | "boxes" | "text" | "none";
  shimComponent: Component;     // async component factory
  mockSampleFactory: (index: number, labelSpace?: string[]) => unknown;
}

export function registerDatasetSchema(schema: DatasetSchemaDescriptor): void { ... }
export function resolveDatasetShim(datasetType: string | null | undefined): Component { ... }
export function getMockSampleFactory(datasetType: string): (...) => unknown { ... }
```

`resolveDatasetShim` falls back to the `image_classification` shim for unknown types.

### 3. Schema Modules: `schemas/`

Each file in `apps/web/src/views/datasets/schemas/` registers one dataset type:

```typescript
// schemas/image-detection.ts
import { registerDatasetSchema } from "../schema-registry";
import { imageDetectionSchema } from "./image-detection-descriptor";

registerDatasetSchema({
  datasetType: "image_detection",
  taskType: "detection",
  annotationType: "boxes",
  shimComponent: defineAsyncComponent(() => import("../shims/DetectionDatasetsShim.vue")),
  mockSampleFactory: imageDetectionSchema.mockSampleFactory,
});
```

The barrel `registry.ts` imports all schema modules so they self-register before the host renders.

### 4. Shared UI Package: `@platform/web-ui`

The `libs/web-ui` package owns reusable UI and helpers independent of routing, API clients, stores, and the widget registry.

- **Normalized Data**: Consistent field types across dataset types.
- **Permissions**: `isSuperadmin`, `canDelete`, etc.
- **UI Components**: `DatasetPageShell`, `DatasetToolbar`, `DatasetTable`, `DatasetRowActions`.
- **Dataset Helpers**: `useDatasetListSurface`, `buildDatasetColumns`.

### 5. Shims

Shims are leaf components defining per-type dataset list layouts using `@platform/web-ui` helpers.

| Shim | Dataset Type | Notes |
|------|-------------|-------|
| `ClassificationDatasetsShim.vue` | `image_classification` | Default fallback shim |
| `VqaDatasetsShim.vue` | `image_vqa` | Extra alert for VQA-specific guidance |
| `DetectionDatasetsShim.vue` | `image_detection` | Object detection list view |

## Backend Schema System

The frontend schema registry mirrors a backend `DatasetSchema` dataclass system:

```
apps/api/app/domain/dataset_schema.py   ← DatasetSchema dataclass
apps/api/app/domain/schema_registry.py  ← register/get/list_all
apps/api/app/domain/schemas/            ← one module per type, auto-registers on import
  __init__.py                           ← imports all schema modules (barrel)
  image_classification.py
  image_vqa.py
  image_detection.py
```

Each Python schema module defines:
- `generate_ls_config(label_space)` — Label Studio XML config
- `platform_annotation_to_ls(label, annotation_value)` — annotation format conversion
- `ls_annotation_to_platform(ls_results)` — reverse conversion
- `mock_item_generator(index, label_space)` — deterministic synthetic sample (shared with seeds and Storybook)

The `mock_item_generator` in the Python schema is the **same logic** as `mockSampleFactory` in the TypeScript schema — a single source of truth for test/mock data across backend seeds, `SchemaAwareMockUpstream`, and frontend Storybook stories.

## Extension Flow: Adding a New Dataset Type

To add a new dataset type end-to-end (e.g., `image_segmentation`):

### Backend

1. **Add enum values** in `apps/api/app/domain/types.py`:
   ```python
   IMAGE_SEGMENTATION = "image_segmentation"
   SEGMENTATION = "segmentation"
   ```

2. **Create the schema module** `apps/api/app/domain/schemas/image_segmentation.py`:
   ```python
   from app.domain.dataset_schema import DatasetSchema
   from app.domain import schema_registry

   SCHEMA = DatasetSchema(
       dataset_type="image_segmentation",
       task_type="segmentation",
       annotation_type="masks",
       label_space_mode="required",
       generate_ls_config=...,
       platform_annotation_to_ls=...,
       ls_annotation_to_platform=...,
       mock_item_generator=...,
   )
   schema_registry.register(SCHEMA)
   ```

3. **Register in the barrel** `apps/api/app/domain/schemas/__init__.py`:
   ```python
   from app.domain.schemas import image_segmentation  # noqa: F401
   ```

### Frontend

4. **Add type values** in `libs/web-ui/src/api/types.ts`:
   ```typescript
   export type TaskType = "classification" | "vqa" | "detection" | "segmentation";
   export type DatasetType = "image_classification" | "image_vqa" | "image_detection" | "image_segmentation";
   ```

5. **Create the shim** `apps/web/src/views/datasets/shims/SegmentationDatasetsShim.vue`.

6. **Create the schema module** `apps/web/src/views/datasets/schemas/image-segmentation.ts`:
   ```typescript
   import { defineAsyncComponent } from "vue";
   import { registerDatasetSchema } from "../schema-registry";

   registerDatasetSchema({
     datasetType: "image_segmentation",
     taskType: "segmentation",
     annotationType: "masks",
     shimComponent: defineAsyncComponent(() => import("../shims/SegmentationDatasetsShim.vue")),
     mockSampleFactory: (index) => ({ /* ... */ }),
   });
   ```

7. **Register in the barrel** `apps/web/src/views/datasets/registry.ts` — add the import.

### Seed script

8. **Create** `libs/seedmaker/src/seedmaker/datasets/image_segmentation.py` using the same `mock_item_generator` logic.

9. **Register** in `libs/seedmaker/src/seedmaker/datasets/__init__.py`.

## Fallback Behavior

If `resolveDatasetShim` receives an unknown `datasetType`, it falls back to `image_classification`. This keeps the list page functional while a new type's shim is being developed.
