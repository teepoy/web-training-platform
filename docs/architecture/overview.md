# Architecture

`CORE_DESIGNS.md` is authoritative. This page is a compact map of the current
runtime and data boundaries.

## Runtime Layers

| Layer               | Location                                    | Responsibility                                                                                                 |
| ------------------- | ------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Control plane       | `apps/api`                                  | HTTP API, auth, capability metadata, compatibility validation, job state, Prefect dispatch, result persistence |
| Orchestration       | Prefect deployments                         | Executes train, predict, train-and-predict, sensor, and other background flows                                 |
| Runtime services    | `services/*` target boundary                | Out-of-process heavy execution consuming manifests and writing artifacts/predictions                           |
| Optional ML library | `libs/ml`                                   | Optional Torch/Ultralytics kernels loaded only by the GPU worker                                               |
| Data plane          | manifest, Arrow/Parquet, signed object refs | Stable dataset view handoff between control plane and runtime                                                  |

```text
dataset storage
  -> versioned view materialization
  -> DataPlaneManifest
  -> Prefect deployment / runtime executable
  -> artifact or prediction writeback
  -> platform job state
```

## Capability Registration

Capability metadata is explicit and separate from executable registration:

```text
module product CapabilityBundle + module runtime capability descriptor
  -> central product/runtime catalog validation
  -> optional environment route override
  -> Prefect deployment
  -> lazy executable adapter
```

- `apps/api/app/modules/types/capabilities.py` defines typed view,
  materializer, trainer, predictor, and bundle descriptors.
- `apps/api/app/modules/sc/capabilities.py` owns SC product metadata.
- `apps/api/app/modules/types/catalog.py` is the central aggregate/query surface.
- `apps/api/app/modules/sc/runtime/descriptor.py` unifies SC executable binding,
  algorithm identity, and default Prefect routes; `app/modules/runtime/catalog.py`
  is their central query surface.
- `apps/api/config/*.yaml` may override environment-specific deployment,
  resource, owner, or code-version values; it does not repeat contracts or
  algorithms.
- `apps/api/app/modules/sc/runtime/` contains Torch-free worker adapters;
  `libs/ml` contains the optional execution kernels.

The API catalog never imports executable modules. Filesystem scanning is not a
registration mechanism.

## View And Materialization Model

A view is identified by one `ViewContractRef`:

- legacy/control-plane `view_id`;
- canonical data-plane contract;
- schema version.

Each version is independently registered and may coexist with other versions.
Canonical Pydantic view rows live under an owning module's
`views/<name>/v<version>/schemas.py` and bind to catalog metadata through
`@view`.

A materializer declares the exact view version it produces and its supported
purpose, transport format, and storage mode. A trainer or predictor declares
the exact view version it consumes. Trainer-to-predictor pairing is explicit;
matching IDs are not used as an implicit relationship.

## Dataset Storage

`storage_mode`, `dataset_type`, and view contract are independent:

- `storage_mode` selects physical storage such as `db_full` or
  `file_shard_sparse`;
- `dataset_type` owns semantic adapters and supported view IDs;
- a materializer projects storage into a versioned data-plane view.

API-internal sample access goes through `DatasetStorageAgg`, opened by
`DatasetStorageFactory`. Out-of-process runtimes consume manifests or stable
data-plane interfaces rather than API repositories, ORM objects, or Python
aggregates.

## Runtime Import Boundary

- API startup, routers, services, composition, and registration code must not
  import `ml_library` or Torch packages.
- Prefect flow code imports the lightweight module-owned adapter only at
  execution time.
- Torch, TorchVision and Ultralytics live only in the optional `libs/ml`.
- New production ML implementations still target out-of-process `services/*`
  runtimes; `libs/ml` is the local worker implementation.

## Product And Operational State

- Prefect is the execution-state source.
- The API database is the product-state source.
- Frontend clients query task/job state through the API.
- Prediction persistence goes through the dataset storage aggregate.
- Label Studio is an explicit annotation/review integration, not prediction
  truth.
- Prometheus carries low-cardinality operational metrics; per-job details
  belong in Prefect, task tracking, and structured logs.

Detailed contracts:

- [Runtime registration](runtime-registration-contract.md)
- [Data-plane manifest](data-plane-manifest-contract.md)
- [Dataset storage modes](dataset-storage-modes.md)
- [Composition](composition-contract.md)
