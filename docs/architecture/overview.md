# Architecture

`CORE_DESIGNS.md` is authoritative. This page is a compact map of the current
runtime and data boundaries.

## Runtime Layers

| Layer                    | Location                                                                        | Responsibility                                                                                        |
| ------------------------ | ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Control plane            | `apps/api`                                                                      | HTTP API, auth, capability queries, compatibility checks, job submission, product state               |
| Execution backend        | Prefect deployments today                                                       | Submission and execution-state transport; not a capability registry or generic algorithm orchestrator |
| Runtime modules/services | `apps/api/app/modules/*/runtime` compatibility handlers and target `services/*` | Own trainer/predictor data strategy and execution                                                     |
| Optional ML library      | `libs/ml`                                                                       | Torch/Ultralytics kernels loaded only inside selected callables                                       |
| Data plane               | module ports, manifests, Arrow/Parquet, signed refs                             | Dataset/view handoff appropriate to local or external execution                                       |

```text
HTTP request
  -> RuntimeRouter registration + route
  -> submission backend
  -> thin runtime host
  -> algorithm-owned dataset/materialization/batch strategy
  -> artifact or prediction writeback
```

## Capability Registration

Trainer/predictor metadata and execution are registered together:

```text
module RuntimeRouter decorators
  -> RuntimeCapabilityCatalog validation
  -> optional environment route override
  -> registered callable
```

- `app/modules/types/catalog.py` owns versioned view definitions and canonical
  row/Arrow schema references.
- `app/modules/runtime/domain/executables.py` provides `RuntimeRouter` and the
  aggregate catalog.
- `app/modules/sc/runtime/` owns SC registrations, callables, and optional
  train-and-predict composition.
- `app/modules/runtime/catalog.py` aggregates module routers as the single
  trainer/predictor metadata, executable, algorithm, and route source.

There is no second executable registry, no metadata-only trainer/predictor
catalog, and no filesystem discovery. Heavy ML libraries are lazy imports in
registered functions.

## Data Strategy Ownership

`storage_mode`, `dataset_type`, and versioned view contracts remain independent.
`DatasetStorageAgg` is the API-internal storage boundary; external runtimes use
stable data-plane interfaces and manifests.

The registered algorithm owns sample selection, dataset construction,
materialization/loading, chunk/batch policy, and output semantics. The platform
does not centrally select a materializer or impose a common trainer/predictor
I/O model. View and model contracts provide compatibility and provenance.

## Product And Operational State

- The execution backend is the execution-state source.
- The API database is the product-state source.
- Frontend clients query job state through the API.
- Prediction persistence goes through the owning algorithm and dataset storage
  boundary.
- Label Studio is an annotation/review integration, not prediction truth.

Detailed contracts:

- [Runtime registration](runtime-registration-contract.md)
- [Runtime execution](runtime-contract.md)
- [Data-plane manifest](data-plane-manifest-contract.md)
- [Dataset storage modes](dataset-storage-modes.md)
- [Composition](composition-contract.md)
