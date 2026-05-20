# Dataset Schema System

The dataset schema system provides a **single source of truth** for each dataset/task type pairing. One `DatasetSchema` descriptor drives type registration, Label Studio config generation, annotation format conversion, mock data generation, and frontend shim resolution — eliminating scattered per-type hard-coding.

## Problem Solved

Before this system, adding a new dataset type required touching 8+ locations independently:
- Hard-coded `ALLOWED_DATASET_TASK_PAIRS` dict in `compatibility.py`
- Manual LS config string in `label_studio.py`
- Annotation conversion switch-cases in multiple services
- Separate mock data functions in seed scripts
- Separate mock data functions in Storybook stories
- Manual shim registry entry in `registry.ts`
- Manual `TaskType`/`DatasetType` union in `types.ts`

Now a single schema module touches all of these via auto-registration.

## Architecture

```
DatasetSchema (Python dataclass)
├── dataset_type / task_type      → DB identifiers, API enums
├── generate_ls_config()          → Label Studio XML
├── platform_annotation_to_ls()   → annotation format (platform → LS)
├── ls_annotation_to_platform()   → annotation format (LS → platform)
├── mock_item_generator()         → deterministic PreviewItem (shared across seeds, upstream, Storybook)
└── metadata_schema               → UI display hints

DatasetSchemaDescriptor (TypeScript interface)
├── datasetType / taskType        → matches Python schema
├── annotationType                → "choice" | "boxes" | "text" | "none"
├── shimComponent                 → async Vue component for dataset list page
└── mockSampleFactory()           → same logic as mock_item_generator (single source of truth)
```

## File Layout

### Backend

```
apps/api/app/domain/
├── dataset_schema.py       ← DatasetSchema dataclass definition
├── schema_registry.py      ← register() / get() / list_all() / get_allowed_pairs()
└── schemas/
    ├── __init__.py         ← barrel: imports all schema modules (triggers auto-registration)
    ├── image_classification.py
    ├── image_vqa.py
    └── image_detection.py
```

### Frontend

```
apps/web/src/views/datasets/
├── schema-registry.ts      ← DatasetSchemaDescriptor, registerDatasetSchema(), resolveDatasetShim()
├── registry.ts             ← imports all schema modules (barrel); re-exports resolveDatasetShim
├── schemas/
│   ├── image-classification.ts
│   ├── image-vqa.ts
│   └── image-detection.ts
└── shims/
    ├── ClassificationDatasetsShim.vue
    ├── VqaDatasetsShim.vue
    └── DetectionDatasetsShim.vue
```

### Types

```
libs/web-ui/src/api/types.ts    ← TaskType / DatasetType union type definitions
apps/api/app/domain/types.py    ← DatasetType / TaskType enum values
```

### Seeds

```
libs/seedmaker/src/seedmaker/datasets/
├── __init__.py             ← barrel (import all dataset modules)
├── image_detection.py      ← uses same box generation logic as mock_item_generator
└── ...
```

## How Services Use the Schema

### `compatibility.py`
`ALLOWED_DATASET_TASK_PAIRS` is now derived from the schema registry:
```python
from app.domain.schema_registry import get_allowed_pairs
ALLOWED_DATASET_TASK_PAIRS = get_allowed_pairs()
```

### `preview_upstream.py`
`SchemaAwareMockUpstream` drives mock items from `schema.mock_item_generator`:
```python
class SchemaAwareMockUpstream(UpstreamAdapter):
    def __init__(self, schema: DatasetSchema, label_space: list[str]):
        self._schema = schema
        self._label_space = label_space

    def get_items(self, limit: int, offset: int) -> list[PreviewItem]:
        return [
            self._schema.mock_item_generator(i, self._label_space)
            for i in range(offset, offset + limit)
        ]
```

### `preview_service.py`
`start_persist()` reads `dataset_type` and `task_type` from the upstream schema instead of hard-coding `image_classification`:
```python
schema = upstream.get_dataset_schema()
dataset_type = schema.dataset_type if schema else "image_classification"
task_type = schema.task_type if schema else "classification"
```

## Annotation Storage

Complex annotation types (e.g., bounding boxes) use the `annotation_value` JSON column added to `AnnotationORM`:

| Column | Type | Use |
|--------|------|-----|
| `label` | `str NOT NULL` | Primary label; backward-compatible (classification uses it; detection sets `""`) |
| `annotation_value` | `JSON nullable` | Complex payload — e.g., `[{"label": "car", "x": 0.1, "y": 0.2, "width": 0.25, "height": 0.2}]` |

`CreateAnnotationRequest` accepts `annotation_value: dict | list | None = None`.

## Mock Data: Single Source of Truth

The `mock_item_generator` in each Python schema and `mockSampleFactory` in the corresponding TypeScript schema use the **same logic**:

```
seed scripts          ─┐
SchemaAwareMockUpstream ├─► mock_item_generator(index, label_space) → PreviewItem / sample dict
Storybook fixtures    ─┘
```

This means: seed data, preview upstream mock data, and Storybook stories all render identically shaped items. A broken schema is caught immediately in Storybook before running the API.

## Registered Types

| `dataset_type` | `task_type` | `annotation_type` | `label_space_mode` |
|---|---|---|---|
| `image_classification` | `classification` | `choice` | `required` |
| `image_vqa` | `vqa` | `text` | `forbidden` |
| `image_detection` | `detection` | `boxes` | `required` |
