# View Contract Foundation

View contracts provide a typed, decoupled interface between dataset storage and model runtimes (trainers and predictors). This foundation allows the platform to support diverse dataset types and model architectures without hard-coded compatibility logic.

## Core Concepts

### 1. View Contract

A **View Contract** defines a specific typed IO shape for a dataset row. It represents a semantic projection of the underlying dataset samples and annotations into a format that a trainer or predictor understands.

In the current implementation, view contracts are **internal backend vocabulary**. They are used for runtime dispatch and validation, but are not yet exposed as public API payloads (which remain Pydantic/JSON based).

### 2. Four-Layer Relationship

The system operates through a structured relationship between storage, semantics, IO, and runtime:

- **StorageMode** (`db_full` | `file_shard_sparse`): Defines how data is physically stored and accessed.
- **DatasetType** (`image_classification` | `image_sc` | etc.): Defines the semantic meaning and schema of the dataset.
- **ViewContract** (`LabeledImageV1` | `QAInputV1` | etc.): Defines the typed IO interface for a specific operation.
- **TrainerSpec / PredictorSpec**: Catalog entries that declare which ViewContracts they require as input and which ModelType they produce or consume.

### 3. Compatibility Equation

The availability of a trainer or predictor for a given dataset is determined by a three-part compatibility check:

```text
available = view-compatible ∩ model-type-compatible ∩ dataset-policy-allowed
```

1.  **View Compatibility**: Does the dataset schema provide all the view types required by the trainer or predictor?
2.  **ModelType Compatibility**: Does the operation involve a model type supported by the runtime and not restricted by the dataset?
3.  **Dataset Policy**: Is the specific trainer, predictor, or model type explicitly denied by the dataset's `RuntimeFilterPolicy`?

## Current Implementation Path

- **Control Plane**: JSON and Pydantic remain the primary path for UI and API interactions.
- **Capability declarations**: Module-owned `CapabilityBundle` values under
  `apps/api/app/modules/types/registrations/` declare versioned views,
  canonical Pydantic row and Arrow schema paths, materializers, trainers,
  predictors, model contracts, and trainer/predictor pairings.
- **Central catalog**: `apps/api/app/modules/types/catalog.py` aggregates the
  bundles and validates IDs, exact view versions, materializer outputs, and
  pairings without importing executable ML modules.
- **Executable compatibility code**: Temporary demo implementations live under
  `apps/api/app/runtime_compat/ml/` and are lazy-loaded only by Prefect flow
  entrypoints through explicit bindings.

## Future and Deferred Scope

The following items are deferred to future development phases (see `view-contract-backlog.md`):

- **Arrow/gRPC**: High-performance columnar data transport for large-scale (`file_shard_sparse`) datasets.
- **Frontend Migration**: Refactoring the web UI to use explicit view contracts for rendering.
- **Public View APIs**: Specialized endpoints for fetching view-specific data (e.g., `GET /datasets/{dataset_id}/views/{view_type}/samples`). The per-view endpoint is **delivered**; full OpenAPI schema support remains deferred.

## What Was Built

The foundation consists of the following components:

**Capability metadata** (`apps/api/app/modules/types/`):

1. `capabilities.py`: typed `ViewContractRef`, view/materializer/trainer/predictor
   descriptors, bundles, and central validation.
2. `registrations/`: module-owned declarations that can be maintained separately.
3. `catalog.py`: central aggregation and query surface.

**View row schemas**:

- Canonical Pydantic row classes live under the owning module's
  `views/<name>/v<version>/schemas.py`.
- `@view(id="...")` only binds a row class to an existing catalog definition.
  Name, annotation semantics, row import path, and Arrow schema import path
  come from that definition; duplicate or mismatched registrations fail.
- API startup imports the catalog-declared row modules. This is explicit
  descriptor-driven loading, not filesystem discovery.
- Dataset types list supported `view_id` values; registration rejects unknown
  catalog views.

**Core registry** (`apps/api/app/core/registry.py`):

- `@view` and `@dataset` decorators with in-memory lookup methods. Executable
  trainer/predictor registration is outside API startup.

**Model compatibility**:

- A trainer produces one versioned `ModelContractRef`.
- Every paired predictor consumes that exact contract.
- Model artifacts persist both contract and schema version; every prediction
  entrypoint validates them before dispatch.

**Model implementations**:

- `apps/api/app/runtime_compat/ml/`: temporary worker-only implementations and
  lazy executable bindings.
- Production implementations belong in out-of-process `services/*` runtimes.

**View service** (`apps/api/app/modules/datasets/`):

- `app/services/view_service.py`: Projects dataset samples into view-type-specific row shapes (e.g. `LabeledImageV1Row`, `QAInputV1Row`).
- `domain/compatibility.py`: `validate_view_for_dataset()` gate that checks whether a view type is compatible with a dataset.

**Per-view API endpoint**: `GET /datasets/{dataset_id}/views/{view_type}/samples` in `port/http/router.py`.

## Image-Bearing View Rows

View rows that contain images should expose stable image references or browser-ready URLs, not raw object-storage internals. For sparse SC v2 datasets, `patch_image_v1` rows carry an `images` list where each image has an `image_id`, semantic `role`, `content_type`, and URL pointing at the dataset image proxy:

```text
/api/v1/datasets/{dataset_id}/samples/{sample_id}/images/{image_id}
```

The API endpoint reads embedded image bytes from the Parquet shard and returns the correct content type. Frontend callers must still wrap browser image URLs with auth query parameters before assigning them to `<img src>`. For SC-specific views, use the helpers in `apps/web/src/features/sc/domain/models.ts`; for generic storage URIs, use `apps/web/src/shared/utils/image-adapters.ts`.
