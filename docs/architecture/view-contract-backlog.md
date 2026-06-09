# View Contract Backlog

> **This document tracks deferred work for the View Contract system.**
> Items listed here are **Not covered in this run** and represent the Phase 2+ roadmap.

## Current Architecture Status

The current implementation uses **JSON/Pydantic** as the primary and only control-plane path for dataset view contracts. This is optimized for UI-driven workflows where pages typically contain ≤~500 rows. The design includes specific "seams" for future batch/stream performance lanes, but the high-performance Arrow/gRPC paths remain reserved for future development.

## Deferred Items

### 1. Advanced Filtering Policies
**Rationale:** Fine-grained control over which trainers and predictors can be used with specific view types or model types. This prevents incompatible configuration combinations at the API level.
**Prerequisites:** Base `ViewContract` registry and `ModelTypeSpec` definitions.
**Keywords:** Regex allow/deny filtering for trainer IDs, predictor IDs, model types, and view types.

### 2. ModelTypeSpec Registry Extraction
**Rationale:** Automating the extraction of model capabilities and requirements from preset metadata to ensure the UI can dynamically adapt to new model types.
**Prerequisites:** Standardized metadata format in trainer/predictor presets.
**Keywords:** Full `ModelTypeSpec` registry extraction from preset/model metadata.

### 3. Runtime Dispatch Decoupling
**Rationale:** Moving away from the monolithic `Preset` runtime flow to a more flexible dispatch system that routes tasks directly to trainers and predictors.
**Prerequisites:** Refactored worker orchestration layer.
**Keywords:** Replacing `Preset` runtime flow with trainer/predictor runtime dispatch.

### 4. Recipe/Preset UX Bundle Model
**Rationale:** Creating higher-level "recipes" that bundle presets with specific UI configurations and default parameters to simplify the user experience.
**Prerequisites:** Stable `ViewContract` and `Preset` definitions.

### 5. Frontend View Contract Migration
**Rationale:** Refactoring the frontend to use explicit UI view contracts instead of the generic `BrowserItem` structure, allowing for type-safe rendering of diverse dataset items.
**Prerequisites:** Backend `ViewContract` API stabilization.
**Keywords:** Frontend migration from `BrowserItem` to explicit UI view contracts.

### 6. Dedicated View API Endpoints
**Rationale:** Providing specialized API endpoints and OpenAPI schemas for fetching view-specific data, improving frontend performance and documentation.
**Prerequisites:** View-specific Pydantic models.
**Keywords:** New API endpoints or OpenAPI schemas for view pages.

### 7. Arrow/Parquet ViewBatch Implementation
**Rationale:** Enabling high-performance data transport for large-scale operations (100k+ rows) by moving from JSON to columnar formats.
**Prerequisites:** `file_shard_sparse` storage mode stabilization.
**Keywords:** Arrow/Parquet `ViewBatch` implementation.

### 8. gRPC Worker Transport
**Rationale:** Using gRPC to carry Arrow batches between the API and workers, reducing serialization overhead and improving throughput.
**Prerequisites:** Arrow/Parquet `ViewBatch` and gRPC infrastructure setup.

### 9. Sparse-Native Lifecycle Operations
**Rationale:** Extending the `file_shard_sparse` mode to support training, prediction review, and export without ever materializing individual database rows.
**Prerequisites:** Shard-level manifest management and Arrow-based processing.
**Keywords:** Sparse-native training, prediction review, export, and annotation storage.

### 10. Non-Image Preview Support
**Rationale:** Generalizing the `PreviewItem` system to support text-only, audio, or other non-image data types.
**Prerequisites:** Content-type aware preview rendering in the frontend.
**Keywords:** Text-only or non-image PreviewItem replacement.

### 11. Schema Versioning & Migration
**Rationale:** Providing a framework for managing changes to dataset schemas and view contracts over time, including data migrations for existing records.
**Prerequisites:** Versioned registry entries for view contracts.
**Keywords:** Dataset schema migration/versioning framework for view contracts.

## Preset-to-Recipe Migration Notes

This section documents the planned transition from the monolithic `Preset` system to a decoupled, flexible runtime architecture.

### Conceptual Future Split

The current `Preset` (a single UX bundle that hard-codes trainers, predictors, and model metadata) will be split into four distinct entities:

1.  **Trainer**: A standalone execution unit that consumes specific `ViewType` inputs and produces a `ModelType`.
2.  **Predictor**: A standalone execution unit that consumes a `ModelType` and an input `ViewType` to produce predictions.
3.  **ModelType**: A registered identifier for a model architecture/weight class that defines compatibility between trainers and predictors.
4.  **Recipe**: The new UX bundle. A Recipe provides the user-facing name, description, and default parameters, but it points to separate `Trainer` and `Predictor` identifiers instead of hard-coding them.

### Migration Strategy

Current `Preset` execution remains the authoritative path for the runtime. The transition will follow these steps:

1.  **Stabilize View Contracts**: (Current Phase) Establish the internal vocabulary for IO and compatibility.
2.  **Trainer/Predictor Dispatch**: Introduce a runtime layer that can execute tasks based on `TrainerSpec` or `PredictorSpec` IDs.
3.  **Deprecate Preset Execution**: Transition the worker logic to use the new dispatch system.
4.  **Introduce Recipes**: Move UI-facing "Preset" definitions to the new `Recipe` model, referencing the decoupled runtimes.

All migration steps beyond the basic view contract foundation are **future/deferred work**.
