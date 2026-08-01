# Runtime Execution Contract

Status: transitional

The removed `apps/worker` and `apps/inference` HTTP topology is no longer the
runtime contract. Prefect deployments are the executable boundary; production
trainer/predictor implementations should run in out-of-process `services/*`
runtimes and exchange versioned manifests and result contracts with the
platform.

## Dispatch

```text
catalog capability
  + module-owned runtime capability descriptor
  -> optional environment route override
  -> Prefect deployment
  -> runtime consumes DataPlaneManifest
  -> runtime writes model artifact or prediction result
  -> API commits product job state
```

Flow parameters contain transport-stable identifiers and contracts:

- platform job ID;
- catalog capability ID;
- canonical input view contract and schema version;
- input manifest or authorized dataset reference;
- output artifact/prediction contract;
- algorithm/code version;
- resource profile.

They must not contain API repositories, ORM rows, dependency-injection
containers, Python callables, or `DatasetStorageAgg` instances.

## Capability And Executable Separation

- Product metadata is aggregated by `app.modules.types.catalog`.
- Executable binding, algorithm identity, and default deployment routes are
  aggregated by `app.modules.runtime.catalog`.
- Input/model contracts are derived from product catalog metadata rather than
  copied into runtime routes.
- `runtime_routing.*_routes` is optional and may override only deployment name,
  resource profile, owner, and code version for an environment.
- Every route declares whether deployment ownership is `local_compat` or
  `external`; the API seeds only local compatibility deployments.
- Prefect deployments are executable capabilities.
- SC repository-local adapters are owned by `app.modules.sc.runtime` and
  imported lazily only by Prefect flow execution.
- Catalog listing and API startup never import `ml_library` or heavy ML packages.
- `ml_library.models` contains private in-process values only. A future external SC
  runtime interface belongs with `libs/protos` and should use protobuf plus
  Arrow schema/manifest definitions rather than Python DTO sharing.

## Data Input

Runtime input is a versioned view manifest defined by
[`data-plane-manifest-contract.md`](data-plane-manifest-contract.md). The view
contract referenced by a trainer/predictor route must exactly match the
`ViewContractRef` in the capability catalog.

Materializers produce manifests for an exact view version. Selection is by:

- view;
- purpose (`train`, `predict`, `preview`, `export`);
- storage mode;
- supported transport format.

No materializer may silently substitute another view or schema version.
Train and predict resolve materializers by the same view/purpose/storage-mode
rule and own temporary materialization cleanup for the execution lifetime.

## Output

Training produces a model bundle plus provenance:

- trainer/catalog ID and version;
- compatible predictor IDs;
- algorithm-specific model contract and schema version;
- input view contract/version;
- algorithm/code version or image digest;
- label space and model format;
- source job ID.

Prediction produces platform prediction rows or a prediction manifest with:

- model and predictor provenance;
- sample identity;
- prediction payload and confidence;
- successful/skipped/failed counters;
- explicit error table/manifest for partial failures.

Train failure is terminal. Prediction may complete partially only when errors
are represented explicitly.

## Authentication And State

- Runtime access uses service credentials plus job-scoped authorization.
- Long-lived user tokens are not Prefect parameters.
- Prefect owns execution state.
- The API owns product job, model, artifact, and prediction state.
- Runtime services report progress/results through stable transport boundaries,
  not shared process memory.

See also:

- [Runtime registration](runtime-registration-contract.md)
- [View contracts](view-contract-foundation.md)
- [Dataset storage modes](dataset-storage-modes.md)
