# Architecture

`CORE_DESIGNS.md` is authoritative. This page is a compact map of the current
runtime and data boundaries.

## Runtime Layers

| Layer                 | Location                                    | Responsibility                                                                                                 |
| --------------------- | ------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Control plane         | `apps/api`                                  | HTTP API, auth, capability metadata, compatibility validation, job state, Prefect dispatch, result persistence |
| Orchestration         | Prefect deployments                         | Executes train, predict, train-and-predict, sensor, and other background flows                                 |
| Runtime services      | `services/*` target boundary                | Out-of-process heavy execution consuming manifests and writing artifacts/predictions                           |
| Compatibility runtime | `apps/api/app/runtime_compat/ml`            | Temporary lazy-loaded demo executables; never imported by API startup or catalog                               |
| Data plane            | manifest, Arrow/Parquet, signed object refs | Stable dataset view handoff between control plane and runtime                                                  |

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
module-owned CapabilityBundle declarations
  -> central CapabilityCatalog validation
  -> config-backed runtime route
  -> Prefect deployment
  -> runtime-only executable binding
```

- `apps/api/app/modules/types/capabilities.py` defines typed view,
  materializer, trainer, predictor, and bundle descriptors.
- `apps/api/app/modules/types/registrations/` contains declarations owned by
  individual domains.
- `apps/api/app/modules/types/catalog.py` is the central aggregate/query surface.
- `apps/api/config/*.yaml` maps catalog IDs to environment-specific Prefect
  deployment routes.
- `apps/api/app/runtime_compat/ml/executable_bindings.py` contains only temporary
  worker-local lazy module paths.

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
  import `app.runtime_compat`.
- Prefect flow code may import the lightweight loader only at execution time.
- Torch, TorchVision, Ultralytics, Transformers, and similar dependencies are
  runtime-only.
- New production ML implementations belong in out-of-process `services/*`
  runtimes, not `runtime_compat`.

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
