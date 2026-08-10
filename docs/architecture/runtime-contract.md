# Runtime Execution Contract

Status: accepted

Trainer and predictor capabilities are complete module-owned registrations.
Prefect is the current submission/execution-state backend, not an independent
executable registry or a generic algorithm orchestrator.

## Execution Boundary

```text
RuntimeRouter registration
  -> optional environment deployment override
  -> submission backend (currently Prefect)
  -> thin runtime host
  -> registered module callable
  -> model artifact or predictions
  -> platform product state
```

The HTTP request path validates and submits jobs; it does not execute registered
callables. The thin runtime host builds `TrainingRuntimeContext`,
`PredictionRuntimeContext`, or `TrainAndPredictRuntimeContext` and invokes the
registration selected by operation and capability ID.

Contexts are dispatch context, not universal algorithm I/O contracts. They carry
platform identities, request options, and the available platform context.
Algorithm modules choose how to construct datasets, materialize/load views,
chunk predictions, invoke model implementations, and construct results.

## Input And Output

There is no mandatory common train/predict input or output shape. A local
compatibility algorithm may use module ports and `DatasetStorageAgg`; an
out-of-process runtime uses the stable data-plane interface, Arrow/Parquet
manifests, signed object references, and generated transport contracts.

The exact view and model contracts in a registration remain compatibility and
provenance facts. They do not force all implementations through one
materializer. Temporary resources are cleaned up by the registered callable
that created them. For local artifact files, cleanup occurs only after the
synchronous event consumer has uploaded the yielded `ArtifactOutput`.

API-local runtime modules are algorithm-first. The current SC runtime has one
`ultralytics` module containing both train and predict; the former ResNet branch
has been removed. The module owns its temporary Parquet/checkpoint directory and
passes plain Parquet paths to `libs/ml`; neither the full checkpoint nor the full
Parquet table becomes one in-memory bytes or row-list value. Only platform I/O
such as source opening and prediction persistence is shared.

Training emits model artifact payload and metadata with trainer,
model-contract/version, predictor compatibility, algorithm provenance, label
space, and source job identity. The platform artifact event sink uploads the
payload and idempotently records the artifact. Prediction persists
sample/model/predictor provenance, payload, confidence, counters, and explicit
errors according to the owning algorithm's failure semantics.

The current SC YOLO callable records one durable `level="epoch"` training event
after every epoch with `epoch`, `total_epochs`, `loss`, `accuracy`, and normalized
`progress`. The training SSE endpoint preserves `epoch`, `metric`, and `status`
as named event types so the frontend can render live progress. Because native
`EventSource` cannot send custom headers, the frontend must build this URL with
the shared auth-query helper so both `token` and `org_id` cross the stream
boundary. The classifier is initialized from the package-local architecture
YAML with the configured seed; worker startup must not depend on downloading
pretrained weights.

## Tasks And Composition

Generic runtime code must not define materialization stages, prediction chunks,
or a fixed train-and-predict pipeline. Algorithm-specific tasks or flows live in
the registered function or its module. A registered train-and-predict callable
may compose that module's registered trainer and predictor explicitly.

## Authentication And State

- Runtime access uses service credentials plus job-scoped authorization.
- Long-lived user tokens are not deployment parameters.
- The execution backend owns execution state.
- The API owns product job, model, artifact, and prediction state.
- External runtimes report through stable transport boundaries, not shared
  process memory or API-internal Python objects.

See also:

- [Runtime registration](runtime-registration-contract.md)
- [Data-plane manifest](data-plane-manifest-contract.md)
- [View contracts](view-contract-foundation.md)
