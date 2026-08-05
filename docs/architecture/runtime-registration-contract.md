# Runtime Registration Contract

Status: accepted
Date: 2026-08-05

This contract defines one registration model for trainer and predictor metadata,
execution, algorithm identity, and deployment routing. `CORE_DESIGNS.md` is
authoritative.

## One Module-Owned Registration

Each algorithm-owning module exposes a `RuntimeRouter`, analogous to an HTTP
router. Decorators register complete capabilities:

```python
SC_RUNTIME_ROUTER = RuntimeRouter()

@SC_RUNTIME_ROUTER.trainer(
    id="resnet50-sc-v1",
    name="ResNet-50 SC Defect Classifier",
    input_view=SC_PATCH_IMAGE_V1,
    output_model=SC_RESNET_MODEL_V1,
    predictor_ids=("resnet50-sc-v1",),
    algo_id="resnet50-sc",
    algo_version="1",
    routes=(TRAIN_ROUTE, TRAIN_AND_PREDICT_ROUTE),
)
async def train(ctx: TrainingRuntimeContext) -> object:
    ...
```

A trainer registration contains:

- product ID and display metadata;
- exact input `ViewContractRef`;
- output `ModelContractRef` and explicit predictor IDs;
- algorithm ID/version;
- executable callable;
- operation routes, and optionally a registered train-and-predict callable.

A predictor registration contains the corresponding input view/model contracts,
algorithm identity, executable callable, and prediction route.

`RuntimeCapabilityCatalog` aggregates module routers and is the single query
surface. It validates duplicate IDs, known views, trainer/predictor pairings,
model contracts, and required routes. Do not create a metadata-only
trainer/predictor catalog, a second executable registry, global
`register_trainer`/`register_predictor` aliases, YAML capability presets, or
filesystem discovery.

View definitions remain metadata-only in the type catalog because they also
bind canonical row and Arrow schemas. The split applies to view schema
registration, not to trainer/predictor capabilities.

## What Routes Mean

`RuntimeRouteDefinition` describes how the platform submits one registered
operation:

- operation (`train`, `predict`, or `train-and-predict`);
- deployment name;
- resource profile;
- deployment owner (`local_compat` or `external`);
- explicit missing-image policy;
- output contract selection.

Routes serve submission, deployment seeding, observability, and environment
deployment overrides. They do not describe the algorithm's internal steps,
materialization pipeline, batching, chunking, or task graph.

Environment configuration may override only deployment name, resource profile,
owner, and code version. View/model contracts, algorithm identity, and failure
policy remain code-owned. The API seeds `local_compat` deployments only;
external runtime packages own `external` deployments.

## Dispatch

```text
request
  -> resolve one RuntimeRouter registration
  -> validate auth, dataset/view/model compatibility, and route availability
  -> persist platform job
  -> submit route to the configured execution backend
  -> runtime host builds a narrow context
  -> invoke the registered callable
```

The current backend uses Prefect deployments, but Prefect is a submission and
execution-state mechanism rather than a second capability registry. A
repository-local Prefect wrapper only validates the route envelope, builds a
runtime context, and invokes the selected registration.

Flow parameters remain transport-safe identifiers and values. Never pass
repositories, ORM rows, injector containers, platform service instances, or
Python callables as deployment parameters.

## Algorithm-Owned Data And Execution Strategy

The registered callable owns all algorithm-specific execution decisions:

- dataset construction and sample selection;
- storage/domain port selection;
- view projection and materialization/loading;
- image validation and failure semantics;
- prediction batch/chunk/concurrency policy;
- output persistence and progress cadence;
- any internal task or flow topology.

The platform does not provide a global materializer registry or resolve a
materializer by `(view, purpose, storage_mode)`. A module may inject and use its
own materializer or data-plane client. No universal train/predict input or output
DTO is required. Runtime contexts carry only relevant platform identity,
request options, and access to the available platform context; the registered
module chooses the concrete ports it needs.

If Prefect `@task` or an algorithm-specific `@flow` is useful, declare and invoke
it explicitly inside the registered callable or in the same algorithm module.
Do not add generic `predict-chunk`, generic materialization tasks, or a central
train-and-predict step graph.

## Import And Process Boundaries

Registration modules must be import-safe. They may contain lightweight Python
callables but must not import Torch, CUDA libraries, model weights, or other
heavy optional dependencies at module import time. Local compatibility handlers
load `ml_library` inside the selected callable. `libs/ml` must not import API
internals.

Production executables may move to `services/*`. An external runtime consumes
generated OpenAPI/protobuf/Arrow/manifest contracts and must not import API
services, repositories, ORM models, FastAPI dependencies, `AppContext`, or the
API injector.

## Required Validation

CI must verify:

- each registration ID is unique;
- every referenced view exists;
- every trainer has at least one paired predictor;
- paired trainer/predictor view and model contracts match exactly;
- every trainer has a training route;
- every predictor has only a prediction route;
- a declared train-and-predict route has a registered callable;
- environment overrides contain no static capability fields;
- generic runtime hosts contain no materializer selection or chunk strategy;
- importing registration modules does not import heavy ML libraries.
