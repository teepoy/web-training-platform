# Datasets Shim Architecture

The `DatasetsView` uses a schema-driven shim architecture to support different UI layouts and behaviors based on the **dataset type** of the datasets being displayed. Each dataset type (e.g., `image_classification`, `image_vqa`, `image_detection`) has a corresponding schema descriptor that bundles its shim component, annotation shape, and mock data factory.

## Overview

The architecture consists of five layers:

1. **Host (`DatasetListView.vue`)**: Thin container — fetches data, resolves active dataset type, renders the shim.
2. **Domain Modules (`src/features/datasets/presentation/dataset-types/`)**: One module per dataset type; each registers its schema and shim on import.
3. **Schema registry (`schema-registry.ts`)**: Map of `dataset_type → DatasetSchemaDescriptor`; provides `resolveDatasetShim()`.
4. **Shared UI/API code (`src/shared/`)**: Reusable Vue/Naive UI components, API clients, and dataset-list helpers.
5. **Shims (`ListShim.vue`)**: Per-module leaf components defining the dataset list layout.

## How It Works

### 1. Host: `DatasetListView.vue`

The host is responsible for:
- Fetching the dataset list via Vue Query.
- Deriving `activeDatasetType` from `datasets[0].dataset_type` (e.g. `"image_classification"`).
- Calling `resolveDatasetShim(activeDatasetType)` to get the correct shim component.
- Rendering `DatasetPageShell` + the resolved shim.

### 2. Schema Registry: `schema-registry.ts`

```typescript
// apps/web/src/features/datasets/presentation/pages/schema-registry.ts

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

### 3. Schema Modules: `src/features/datasets/presentation/dataset-types/`

Each dataset type module registers its schema and shim:

```typescript
// src/features/datasets/presentation/dataset-types/detection/views/schema.ts
import { registerDatasetSchema } from "@/features/datasets/presentation/pages/schema-registry";

registerDatasetSchema({
  datasetType: "image_detection",
  taskType: "detection",
  annotationType: "boxes",
  shimComponent: defineAsyncComponent(() => import("./ListShim.vue")),
  mockSampleFactory: (index) => ({ /* ... */ }),
});
```

The app-level `src/app/registrations.ts` imports each module's registration barrel so they self-register during app bootstrap.

### 4. Shared UI/API code: `src/shared/`

The `src/shared/` directory contains reusable UI components, API clients, and helpers independent of specific domain modules.

- **Normalized Data**: Consistent field types across dataset types.
- **Permissions**: `isSuperadmin`, `canDelete`, etc.
- **UI Components**: `DatasetPageShell`, `DatasetToolbar`, `DatasetTable`, `DatasetRowActions`.
- **Dataset Helpers**: `useDatasetListSurface`, `buildDatasetColumns`.

### 5. Shims

Shims are per-module components defining per-type dataset list layouts using `src/shared/` helpers.

| Shim | Dataset Type | Location |
|------|-------------|----------|
| `ListShim.vue` | `image_classification` | `src/features/datasets/presentation/dataset-types/classification/views/` |
| `ListShim.vue` | `image_vqa` | `src/features/datasets/presentation/dataset-types/vqa/views/` |
| `ListShim.vue` | `image_detection` | `src/features/datasets/presentation/dataset-types/detection/views/` |

## Backend Schema System

The frontend schema registry mirrors a backend `DatasetSchema` dataclass system:

```
apps/api/app/domain/dataset_schema.py   ← DatasetSchema dataclass
apps/api/app/domain/schema_registry.py  ← register/get/list_all
apps/api/app/modules/dataset_classification/domain/schema.py  ← classification schema module
apps/api/app/modules/dataset_detection/domain/schema.py       ← detection schema module
apps/api/app/modules/dataset_vqa/domain/schema.py             ← vqa schema module
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

2. **Create the schema module** `apps/api/app/modules/dataset_segmentation/domain/schema.py`:
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

3. **Import the module from `apps/api/app/main.py`** so it registers on import, matching the existing type-module bootstrap pattern.

### Frontend

4. **Add type values** in `src/types.ts`:
   ```typescript
   export type TaskType = "classification" | "vqa" | "detection" | "segmentation";
   export type DatasetType = "image_classification" | "image_vqa" | "image_detection" | "image_segmentation";
   ```

5. **Create the shim** `src/features/datasets/presentation/dataset-types/segmentation/views/ListShim.vue`.

6. **Create the schema module** `src/features/datasets/presentation/dataset-types/segmentation/views/schema.ts`:
   ```typescript
   import { defineAsyncComponent } from "vue";
   import { registerDatasetSchema } from "@/features/datasets/presentation/pages/schema-registry";

   registerDatasetSchema({
     datasetType: "image_segmentation",
     taskType: "segmentation",
     annotationType: "masks",
     shimComponent: defineAsyncComponent(() => import("./ListShim.vue")),
     mockSampleFactory: (index) => ({ /* ... */ }),
   });
   ```

7. **Register in the app** `src/app/registrations.ts` — add the import:
   ```typescript
   import "../features/datasets/presentation/dataset-types/segmentation/registrations";
   ```

### Seed script

8. **Create** `libs/seedmaker/src/seedmaker/datasets/image_segmentation.py` using the same `mock_item_generator` logic.

9. **Register** in `libs/seedmaker/src/seedmaker/datasets/__init__.py`.

## Fallback Behavior

If `resolveDatasetShim` receives an unknown `datasetType`, it falls back to `image_classification`. This keeps the list page functional while a new type's shim is being developed.
