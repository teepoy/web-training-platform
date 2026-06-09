# View Contract Foundation

View contracts provide a typed, decoupled interface between dataset storage and model runtimes (trainers and predictors). This foundation allows the platform to support diverse dataset types and model architectures without hard-coded compatibility logic.

## Core Concepts

### 1. View Contract
A **View Contract** defines a specific typed IO shape for a dataset row. It represents a semantic projection of the underlying dataset samples and annotations into a format that a trainer or predictor understands.

In the current implementation, view contracts are **internal backend vocabulary**. They are used for runtime dispatch and validation, but are not yet exposed as public API payloads (which remain Pydantic/JSON based).

### 2. Four-Layer Relationship
The system operates through a structured relationship between storage, semantics, IO, and runtime:

*   **StorageMode** (`db_full` | `file_shard_sparse`): Defines how data is physically stored and accessed.
*   **DatasetType** (`image_classification` | `image_vqa` | etc.): Defines the semantic meaning and schema of the dataset.
*   **ViewContract** (`LabeledImageV1` | `QAInputV1` | etc.): Defines the typed IO interface for a specific operation.
*   **TrainerSpec / PredictorSpec**: Catalog entries that declare which ViewContracts they require as input and which ModelType they produce or consume.

### 3. Compatibility Equation
The availability of a trainer or predictor for a given dataset is determined by a three-part compatibility check:

```text
available = view-compatible ∩ model-type-compatible ∩ dataset-policy-allowed
```

1.  **View Compatibility**: Does the dataset schema provide all the view types required by the trainer or predictor?
2.  **ModelType Compatibility**: Does the operation involve a model type supported by the runtime and not restricted by the dataset?
3.  **Dataset Policy**: Is the specific trainer, predictor, or model type explicitly denied by the dataset's `RuntimeFilterPolicy`?

## Current Implementation Path

*   **Control Plane**: JSON and Pydantic remain the primary path for UI and API interactions. View contracts currently map internal data structures to these Pydantic models.
*   **Internal Registries**: Trainer and predictor specifications are maintained via `@trainer` and `@predictor` decorators in `apps/api/app/core/registry.py`. Registered types live under `apps/api/app/modules/types/` (views, trainers, predictors, datasets).
*   **Built-in Specs**: The foundation includes pre-registered specs for `resnet50-cls-v1`, `clip-zero-shot-v1`, and `dspy-vqa-v1` to validate the architecture.

## Future and Deferred Scope

The following items are deferred to future development phases (see `view-contract-backlog.md`):

*   **Arrow/gRPC**: High-performance columnar data transport for large-scale (`file_shard_sparse`) datasets.
*   **Frontend Migration**: Refactoring the web UI to use explicit view contracts for rendering.
*   **Public View APIs**: Specialized endpoints for fetching view-specific data (e.g., `GET /datasets/{dataset_id}/views/{view_type}/samples`). The per-view endpoint is **delivered**; full OpenAPI schema support remains deferred.

## What Was Built

The foundation consists of the following components:

**Type registrations** (`apps/api/app/modules/types/`):
1. `views/`: View type definitions (e.g. `image_input_v1`, `labeled_image_v1`, `box_detection_v1`, `qa_input_v1`). Each file is a `@view`-decorated class — one .py per view type.
2. `trainers/`: Trainer wrappers decorated with `@trainer(id, name, view_id)`, referencing implementations from `libs/ml/`.
3. `predictors/`: Predictor wrappers decorated with `@predictor(id, name, view_id)`, referencing implementations from `libs/ml/`.
4. `datasets/`: Dataset type classes decorated with `@dataset(id, name, view_types)`.

**Core registry** (`apps/api/app/core/registry.py`):
- `@view`, `@trainer`, `@predictor`, `@dataset` decorators with in-memory lookup methods.

**Model implementations** (`libs/ml/`):
- `libs/ml/domain.py`: `ViewType` and `ModelType` enumerations.
- `libs/ml/classification/`, `libs/ml/detection/`, `libs/ml/vqa/`: Trainer and predictor implementations per modality.

**View service** (`apps/api/app/modules/datasets/`):
- `app/services/view_service.py`: Projects dataset samples into view-type-specific row shapes (e.g. `LabeledImageV1Row`, `QAInputV1Row`).
- `domain/compatibility.py`: `validate_view_for_dataset()` gate that checks whether a view type is compatible with a dataset.

**Per-view API endpoint**: `GET /datasets/{dataset_id}/views/{view_type}/samples` in `port/http/router.py`.

## Image-Bearing View Rows

View rows that contain images should expose stable image references or browser-ready URLs, not raw object-storage internals. For sparse SC v2 datasets, `patch_image_v1` rows carry an `images` list where each image has an `image_id`, semantic `role`, `content_type`, and URL pointing at the dataset image proxy:

```text
/api/v1/samples/{sample_id}/images/{image_id}?dataset_id={dataset_id}
```

The API endpoint reads embedded image bytes from the Parquet shard and returns the correct content type. Frontend callers must still wrap browser image URLs with auth query parameters before assigning them to `<img src>`. For SC-specific views, use the helpers in `apps/web/src/features/sc/domain/models.ts`; for generic storage URIs, use `apps/web/src/shared/utils/image-adapters.ts`.
