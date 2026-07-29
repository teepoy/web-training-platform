# 0001: Runtime Services + Data Plane Refactor

**Status**: implementation complete — ready for final evaluation
**Date**: 2026-06-18
**Supersedes**:

- `0001-storage-domain-module-extraction.md`
- `0002-materializer-refactor.md`

## Direction

This refactor keeps Prefect as the execution engine while moving trainer/predictor/materializer execution behind explicit runtime/data-plane boundaries.

The old plans had useful local details, but they mixed several decisions that now need to be ordered differently:

- storage extraction,
- materializer extraction,
- trainer/predictor runtime execution,
- image streaming fixes,
- module composition,
- registration/routing.

This merged plan keeps the high-value pieces and defers low-level call-site details to implementation steps.

## Contracts That Must Land First

1. `docs/architecture/composition-contract.md`

   Establish API composition using `injector` and interface-only cross-module injection.

2. `docs/architecture/runtime-registration-contract.md`

   Establish API catalog -> Prefect deployment routing -> data-plane contract.

3. `docs/architecture/data-plane-manifest-contract.md`

   Establish table-first manifests, Arrow/Polars schema ownership, auth, cleanup, prediction writeback, and artifact provenance.

These contracts should land before broad code movement.

## Phase 0: Composition Baseline

Goal: make later module extraction obey the new dependency shape.

Required outcomes:

- API composition root uses `injector`.
- Modules expose public Protocol ports from `port/local` or `domain`.
- Cross-module dependencies inject interfaces only.
- Concrete service/repository/adapter classes stay private to owning modules.
- Tests can override major interface bindings.

Do not start storage/materializer movement until this is in place, or the old concrete service coupling will simply move to new packages.

Implemented checkpoint:

- legacy `AppContainer` / `build_flow_container` removed;
- flow lifecycle is owned explicitly by `build_flow_app_context` / `close_flow_app_context`;
- training and prediction workflows resolve cross-module capabilities through injector-bound Protocols instead of sibling `AppContext` fields;
- dataset storage, sparse import writer, training execution, prediction execution, model catalog, and schedule management expose local ports;
- agent, SC, preview, classify, prediction, task tracker, and Perspective consumers use those ports across module boundaries;
- architecture tests reject legacy container symbols, production sibling-context access, and agent imports of sibling service implementations.

## Phase 1: Runtime Registration + Prefect Routing

Goal: remove ambiguity around trainer/predictor registration after execution moves out of API internals.

Required outcomes:

- API trainer/predictor catalog contains metadata only.
- Prefect deployments are the executable capability boundary.
- Deployment granularity is by capability/resource profile, for example `train.sc-resnet.gpu` and `predict.sc-resnet.gpu`.
- API resolves catalog id -> Prefect deployment by config-backed routing descriptor.
- Flow run parameters use stable data-plane refs and contracts.
- No API service/repository/ORM/Python callable is passed into runtime execution.

Dynamic runtime capability discovery is explicitly out of scope until Prefect deployments are not enough.

Implemented checkpoint:

- added a runtime module with `RuntimeRoutingPort` and config-backed routing descriptors;
- added explicit `runtime_routing` config for trainer, predictor, embedding, and train+predict deployments;
- training, prediction, and train+predict dispatch resolve catalog id -> Prefect deployment through the routing port;
- startup Prefect deployment seeding derives runtime deployments from the same routing config instead of repeating deployment names;
- API catalog fallback stubs no longer map catalog ids to executable module imports;
- architecture and routing tests guard the metadata-only catalog boundary and routing config parsing.

## Phase 2: Storage Domain Module Extraction

Goal: extract physical storage ownership out of `datasets` into a dedicated storage module.

Target module:

```text
apps/api/app/modules/storage/
├── container.py
├── domain/
│   └── storage_agg.py
├── adapter/
│   ├── factory.py
│   ├── db_full/storage.py
│   ├── sparse/storage.py
│   ├── sparse/payload_store.py
│   ├── sparse/reader.py
│   ├── sparse/annotations.py
│   ├── sparse/import_operator.py
│   ├── sparse/parquet_helpers.py
│   └── materialize.py
├── port/local/
│   └── _protocols.py
└── tests/
```

Keep:

- storage implementations,
- sparse payload store,
- manifest reader,
- sparse annotation store,
- sparse import operator,
- materialize/as_hf storage-level helpers.

Move out of `libs/platform-runtime/sparse` everything that is implementation rather than cross-process contract.

Leave in `libs/platform-runtime/sparse`:

- manifest DTOs,
- shard/sample locator DTOs,
- sparse prediction DTOs,
- other transport-stable models.

Public surface:

- expose a narrow storage factory interface,
- do not expose payload store/reader/annotation store to sibling modules,
- consumers open storage through the storage module port.

Implementation details from the old storage plan are still useful, but update them to obey the composition contract:

- no `StorageContext` concrete dependency across modules,
- no sibling module reads through `AppContext.storage`,
- inject `DatasetStorageFactoryPort` or narrower ports.

Implemented checkpoint:

- added `app.modules.storage` with `StorageContext`, storage domain models, storage adapters, and local storage ports;
- moved `DatasetStorageAgg`, `DatasetStorageFactory`, db-full storage, sparse storage, and sparse import operator implementations under the storage module;
- changed `init_datasets` so datasets receives repository and storage capabilities from composition instead of constructing physical storage itself;
- added storage injector bindings for `StorageContext`, `DatasetStorageFactoryPort`, `DatasetPayloadStore`, and `SparseImportWriterFactoryPort`;
- updated prediction, SC, datasets, preview, classify, agent, training flow, and test consumers to resolve storage through the storage module or injected ports;
- kept compatibility shims at the old datasets storage import paths so backward imports can be removed deliberately in a later cleanup;
- added architecture tests that reject production imports from old datasets storage implementation paths and reject production reads of storage members from datasets context.

## Phase 3: Data Plane View Contract

Goal: give runtime execution a stable dataset input boundary.

Required outcomes:

- Define a data-plane request/manifest shape for trainer/predictor inputs.
- Use `docs/architecture/data-plane-manifest-contract.md` as the first manifest contract.
- Support view contract id and schema version.
- Include labels and image role requirements.
- Prefer Parquet/Arrow shard manifests and signed refs for large data.
- Support Arrow Flight as an IPC/streaming option for temporary data and prediction paths.
- Keep small RPC/HTTP streaming as an optimization, not the only large-data path.
- Main transfer path must be LazyFrame/DataFrame/Arrow Table based.
- DTO-like wrappers may carry schema/capability/manifest metadata, but must wrap/reference table objects or table schemas instead of converting samples into dataclass/Pydantic row lists.
- LazyFrame is preferred close to data loading; consumers may use LazyFrame, DataFrame, or Arrow Table depending on execution needs.
- No Python `for` loops over sample rows unless the data is explicitly bounded and known small.

Runtime execution must not import:

- `DatasetStorageAgg`,
- `DatasetStorageFactory`,
- `SampleORM`,
- API repositories,
- API services.

This phase should reuse storage module internals behind API/data-plane adapters.

View contract code owns semantic projection. Manifest contract code owns transport metadata. The coupling belongs in data-plane adapter validation code, not in trainer/predictor implementations.

Implemented checkpoint:

- added `app.modules.data_plane` with a `DataPlaneContext` and injector-bound `DataPlaneSchemaRegistryPort`;
- added code-first Arrow schemas for SC patch image, SC review image, labeled image, box detection, and QA input view contracts;
- added table-first `DataPlaneViewRequest`, `DataPlaneManifest`, shard refs, Arrow Flight endpoint refs, auth metadata, image roles, and label column metadata;
- added manifest transport validation for shard-backed and Arrow Flight manifests;
- added manifest/schema validation that checks `schema_ref` and manifest columns against the registered Arrow schema;
- added `DataPlaneViewMaterializerPort` as the future materializer boundary;
- added architecture tests preventing the data-plane contract module from importing storage implementations, API service classes, repositories, or ORM internals.

## Phase 4: Materializer Module

Goal: consolidate image/materialization logic and stop trainer/predictor-specific one-off image fetch paths.

Target API module:

```text
apps/api/app/modules/materializer/
├── domain/materializer.py
├── app/services/materializer_service.py
├── port/local/
└── tests/
```

Materializer is a data-plane capability in its own module. It may use storage ports, but must not depend on storage implementation classes.

Core interface:

```python
class MaterializerPort(Protocol):
    async def materialize(
        self,
        view,
        *,
        image_roles: list[str],
        output,
    ) -> MaterializationRef: ...
```

The old materializer plan's implementation details are useful but must be adjusted:

- do not depend on concrete `ScImageFetcher` across modules; inject an image/source Protocol,
- do not wire through `AppContext.materializer`,
- do not pass materializer service instances into trainer/predictor callables,
- materialization output should be a stable ref/manifest that runtime can consume.
- materializer internals should operate on LazyFrame/DataFrame/Arrow batches and streaming writers, not `list(df.iter_rows(...))` or per-row DTO conversion.
- image joins should be bulk/batch/stream aligned to table columns; per-image loops are allowed only inside bounded batch adapters where the batch size is explicit.
- train inputs should include embedded image bytes in materialized shards when practical.
- predict inputs may use embedded bytes, signed refs, or Arrow Flight, but the predict data-plane must provide missing-data completion and local Arrow table/shard writing when the model/DataLoader requires it.
- temporary materialized shards/manifests are job-scoped and require TTL cleanup or explicit finalizer cleanup.

Short-term implementation may still create local Parquet shards, but the boundary should already look like a data-plane artifact.

Implemented checkpoint:

- added `app.modules.materializer` with `MaterializerContext` and local materializer ports;
- moved the SC inspection materializer implementation out of `sc.app.services` and left the old SC path as a compatibility shim;
- bound `ScInspectionMaterializerPort` through injector;
- changed prediction flow to resolve SC materialization through the materializer port instead of constructing the concrete materializer directly;
- added architecture tests that reject production imports from the old SC materializer implementation path;
- SC materializer now writes parquet with the registered `sc.patch_image.v1` data-plane columns, including `test_id`;
- SC materializer now returns a `DataPlaneManifest` with schema ref, shard ref, image roles, label columns, row count, dataset id, and job id;
- deferred the remaining SC materializer row-loop/bulk-fetch rewrite, object-storage shard writing, and TTL/finalizer cleanup to the next materializer pass.

## Phase 5: Trainer/Predictor Runtime Execution

Goal: split heavy train/predict execution from API internals while keeping Prefect as execution engine.

Required outcomes:

- Trainer and predictor execution should move under root `services/*` runtime services or equivalent service packages. The API process remains control-plane only.
- Keep `libs/ml` as the pure ML library for now. Runtime services may depend on it for model definitions/training/prediction primitives. Do not delete or absorb `libs/ml` until the service split proves that the library boundary no longer pays for itself.
- `libs/ml` must remain free of API, Prefect, DB ORM, and FastAPI dependencies.
- API creates platform job and Prefect flow run.
- Prefect deployment routes to the correct runtime worker/service.
- Runtime receives only stable parameters: `job_id`, catalog id/version, params, input manifest/view request, output contract.
- Runtime imports `libs/ml` and heavy dependencies locally.
- Runtime reports progress and writes artifacts/predictions through stable contracts.
- Runtime uses service credentials plus job-scoped authorization.
- Resource profiles are `cpu` and `gpu` first.
- Train jobs fail fast on data preparation/schema/required image failures.
- Predict jobs may complete partially; missing images are skipped and skipped samples produce no prediction result.
- Prediction writeback should be table-first via Parquet/Arrow prediction manifest, with gRPC streaming as a batch-oriented option.
- Train/predict job records must store Prefect flow/deployment version, code version or image digest, algo id/version, catalog id/version, and artifact contract.

The old trainer/predictor plan's local improvements remain valid:

- replace per-image `asyncio.gather(get_image_bytes(...))` with streaming or manifest-based bulk access,
- avoid loading all predictor input rows/images into memory,
- use shard/DataLoader style streaming,
- move image decode/preprocess into `torch.utils.data.Dataset` / `DataLoader` workers instead of the orchestration loop,
- manage temp resources explicitly.

But those changes should be applied inside the runtime/data-plane shape, not by passing API concrete services into flow callables.

Implemented checkpoint:

- moved data-plane manifest DTOs into `platform_runtime.data_plane` so runtime services can consume them without importing API modules;
- added `TrainRuntimeRequest`, `PredictRuntimeRequest`, and artifact provenance DTOs to `platform_runtime.contracts`;
- added `services/runtime-services` as a workspace package for trainer/predictor runtime service boundaries;
- runtime service skeletons consume only `platform-runtime` request/manifest contracts and runtime-local algorithm registries;
- added runtime-service tests and architecture guardrails that reject API/FastAPI/ORM imports from runtime contract packages.

## Phase 6: SC Upstream / Image Parser Fixes

Goal: fix known blocking/streaming issues without letting them dictate API module boundaries.

Carry forward from the old materializer plan:

- fix Arrow Flight `do_get()` event loop handling,
- distinguish gRPC aio context from Arrow Flight context,
- replace image-parser async warmer dependence with explicit look-ahead or deterministic stream behavior,
- prefer bulk/streaming image access over one gRPC call per image.

These can be implemented alongside Phase 4/5 as service-local fixes.

Implemented checkpoint:

- tightened SC Arrow Flight ticket parsing and validation for `list_samples`;
- kept Arrow Flight `do_get()` on the synchronous Flight server path and distinct from async gRPC service handlers;
- added service-local tests for invalid Flight tickets and retained existing cache/lock streaming tests.

## Phase 7: Cleanup

Remove or rewrite:

- executable trainer/predictor callable imports from API catalog,
- old concrete cross-module service injection,
- `AppContext.<sibling>.some_service` usage,
- payload store/reader direct imports outside storage internals,
- runtime materialization fallbacks that bypass storage/data-plane contracts,
- obsolete opencode plan details superseded by this merged plan.

Implemented checkpoint:

- removed legacy datasets storage compatibility shims after production imports moved to `app.modules.storage`;
- removed the legacy SC materializer compatibility shim after production imports moved to `app.modules.materializer`;
- added architecture tests that assert removed shim files stay removed;
- added architecture tests that `platform-runtime` and `runtime-services` do not import API internals;
- retained deeper payload-store/reader implementation movement from `platform_runtime.sparse` as stable sparse-contract cleanup because current API sparse routes and tests still use those transport models directly.

## Verification

For docs/contracts:

- no tests required.

For API refactor phases:

- `ruff check apps/api`
- `uv run --directory apps/api pyright .`
- targeted API tests for touched modules
- `make test` before handing off broad backend changes

For API contract changes:

- `make generate`
- OpenAPI sync checks through `make test`

For runtime services:

- service-local checks from `services/AGENTS.md`
- narrow smoke tests for Prefect deployment routing and data-plane manifest consumption

## Explicitly Deferred Details

These are implementation details to decide during the next step:

- exact injector module file layout,
- exact trainer/predictor service packaging,
- specific old call-site migration order.
