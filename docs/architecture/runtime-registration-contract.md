# Runtime Registration Contract

Status: draft
Date: 2026-06-18

This contract defines how trainer and predictor capabilities are registered after splitting execution into runtime services while keeping Prefect as the execution engine.

## Goals

- Keep Prefect as the execution engine.
- Keep API trainer/predictor catalog free of executable callables and heavy ML imports.
- Use Prefect deployments as the runtime capability boundary.
- Route jobs through stable data-plane contracts and object-store manifests.
- Use config-backed routing descriptors for the first version.

## Core Model

Runtime registration has three surfaces:

1. **API Catalog**

   Product/control-plane metadata only:
   - trainer/predictor id
   - display name
   - parameter schema
   - supported task/view/data contracts
   - compatibility and authorization rules
   - default routing hints

   The API catalog must not import executable trainer/predictor callables.
   Catalog entries are typed Python metadata descriptors so parameter and
   compatibility validation can share the API type system. They are not YAML
   presets and do not identify importable implementation modules.

   The catalog is assembled from module-owned `CapabilityBundle` declarations.
   This allows a domain module to keep its declarations nearby while retaining
   one central validation surface. A bundle may declare:
   - versioned view definitions, including canonical row type and Arrow schema
     import paths;
   - materializers that produce an exact view version;
   - trainers and predictors that consume an exact view version and matching
     versioned model contract;
   - explicit trainer-to-predictor pairings.

   Registration is explicit. Filesystem scanning and executable import side
   effects are not capability discovery mechanisms. API startup imports view
   row modules from the paths in the explicit catalog, so there is no second
   hand-maintained view import list.

2. **Prefect Deployment Routing**

   Prefect deployments are the executable capability source of truth.

   A deployment represents an executable runtime capability such as:
   - `train.sc-resnet.gpu`
   - `predict.sc-resnet.gpu`
   - `materialize.sc-patch-image.cpu`

   Deployment granularity is by capability and resource profile. API dispatch resolves a catalog entry to a Prefect deployment by config-backed routing descriptor in the first version. DB-backed routing can come later if runtime routing needs UI editing, dynamic rollout, or audit workflows.

3. **Data Plane Contract**

   Dataset input and result output cross a stable data-plane boundary:
   - view contract id and schema version
   - labels and image role requirements
   - manifest format, preferably Parquet/Arrow plus signed refs for large data
   - artifact output contract
   - prediction writeback contract

   Normative contract: `docs/architecture/data-plane-manifest-contract.md`.

## Dispatch Flow

```text
API receives train/predict request
  -> resolve API catalog entry
  -> validate params, auth, dataset compatibility
  -> validate required data-plane view contract
  -> resolve Prefect deployment routing
  -> create platform job record
  -> prepare or authorize input manifest / view request
  -> create Prefect flow run with stable parameters
  -> runtime reports progress and writes artifacts/predictions
  -> API commits final product state
```

Prefect flow run parameters must be transport-stable:

```json
{
  "job_id": "job_123",
  "catalog_id": "sc-resnet-classifier",
  "catalog_version": "1",
  "params": {},
  "input": {
    "view_contract": "sc.patch_image.v1",
    "manifest_ref": "s3://...",
    "dataset_id": "ds_123"
  },
  "output": {
    "artifact_contract": "model.bundle.v1",
    "model_contract": "sc.resnet50.model.v1",
    "prediction_contract": "sample.predictions.v1"
  }
}
```

Do not pass API service instances, repositories, ORM objects, `DatasetStorageAgg`, or Python callables as flow parameters.

## Routing Descriptor

First version may be config or DB-backed metadata:

```yaml
# yaml-language-server: $schema=./runtime-routing.schema.json
training_routes:
  resnet50-sc-v1:
    deployment: train.sc-resnet.gpu
    input_contract: sc.patch_image.v1
    output_contract: sc.resnet50.model.v1
    resource_profile: gpu
    owner: external
    algo_id: sc-resnet
    algo_version: "1"
    missing_image_policy: fail

prediction_routes:
  resnet50-sc-v1:
    deployment: predict.sc-resnet.gpu
    input_contract: sc.patch_image.v1
    output_contract: sample.predictions.v1
    resource_profile: gpu
    owner: external
    algo_id: sc-resnet
    algo_version: "1"
    missing_image_policy: skip

train_and_predict_routes:
  resnet50-sc-v1:
    deployment: train-and-predict.sc-resnet.gpu
    input_contract: sc.patch_image.v1
    output_contract: sample.predictions.v1
    resource_profile: gpu
    owner: external
    algo_id: sc-resnet
    algo_version: "1"
    missing_image_policy: skip

materialization_routes:
  sc-inspection-patch-image-v1:
    deployment: materialize.sc-patch-image.cpu
    input_contract: sc.patch_image.v1
    output_contract: data-plane-manifest.v1
    resource_profile: cpu
    owner: external
```

The descriptor maps product catalog ids to executable Prefect deployment names. It is not an executable registry. The descriptor schema is a code-reviewed guardrail for editors; Python parsing should validate it before use.

`owner` is mandatory. `local_compat` means the repository-local compatibility
flow owns the deployment and the API may seed it in development. `external`
means another runtime package owns deployment creation and executable code; the
API routes to it but never imports or seeds it.

For the temporary API-local demo runtime, executable module imports are listed
under `app.runtime_compat.ml` in a separate worker-local binding table. The
binding contains catalog ID, kind, and lazy module path only. It is loaded only
by Prefect flow code after routing has selected the capability, never by API
catalog/listing/startup code. It is compatibility scaffolding, not the
long-term runtime capability source of truth; Prefect deployments remain that
boundary.

## View And Materialization Relationships

```text
Dataset storage
  -> materializer(view + version, purpose, storage mode)
  -> DataPlaneManifest(view contract + schema version)
  -> trainer or predictor consuming the same ViewContractRef
```

A view has two identities during the legacy API transition:

- `view_id`, used by dataset adapters and API compatibility checks;
- canonical data-plane `contract` plus `schema_version`, used in routing and
  manifests.

Both identities live in one `ViewContractRef`; call sites must not translate
them through ad-hoc dictionaries. A future v2 is a new descriptor and may
coexist with v1. A materializer cannot claim to produce an undeclared view
version. Trainer/predictor pairing requires the same exact `ViewContractRef`
and `ModelContractRef`.

Materializer selection is independent from trainer selection. Multiple
materializers may produce the same view for different storage modes, purposes,
or transports. A trainer does not name one materializer; orchestration resolves
the materializer by the requested view, purpose, and storage mode.
Train and predict use the same resolution rule and keep the resulting
materialization in an execution-scoped exit stack so temporary shards are
cleaned after completion or failure.

CI must cross-check catalog entries and routing descriptors:

- every catalog trainer has training and train-and-predict routes;
- every catalog predictor has a prediction route;
- route input contracts match the catalog view contract;
- training route output contracts match the trainer model contract;
- every trainer's explicit predictor pairing resolves;
- paired trainers and predictors use the same model contract;
- worker-local executable bindings reference existing catalog entries.

## Deployment Metadata

Where feasible, Prefect deployments should carry equivalent metadata in deployment description/tags/parameters:

- `kind=train|predict|materialize`
- `catalog_id`
- `input_contract`
- `output_contract`
- `owner=local_compat|external`
- `resource_profile`
- `runtime_service`
- `runtime_version`
- `algo_id`
- `algo_version`
- `code_version` or image digest

If Prefect metadata is inconvenient to query, API-side routing descriptors remain acceptable as the source of routing truth.

## Boundaries

- API catalog code may define metadata, schemas, and compatibility. It must not import Torch or runtime executable callables.
- Runtime flow code may import heavy ML libraries inside runtime services/workers. It must not import API module internals.
- Trainer and predictor execution should move to root `services/*` runtime services or equivalent service packages once there is a concrete runtime consumer. Do not keep a standalone shared ML package just for possible reuse. Current in-repository demo implementations are isolated under `apps/api/app/runtime_compat/ml`; they are compatibility code and not a stable cross-process library.
- Runtime code reads inputs through data-plane contracts/manifests, not through direct API Python aggregates.
- Prediction/artifact writes go through stable writeback contracts.
- Prefect remains the execution engine, but frontend and product state continue to go through the platform API.
- Runtime access uses service credentials plus job-scoped authorization. Do not pass long-lived user tokens through Prefect parameters.
- Resource profiles are `cpu` and `gpu` in the first version.
- Every image-bearing train/predict route declares `missing_image_policy`
  explicitly. There is no global implicit default.
- Under `skip`, skipped samples do not produce prediction results.
- Train jobs fail fast on required data/image/schema failures. Predict jobs may complete partially with counters and an error table/manifest.
- Train/predict job records must store flow/deployment version, code version or image digest, algo id, algo version, catalog id, and catalog version.
- Local development should reuse the existing Prefect GPU worker target under a runtime-oriented name.

## When To Add Dynamic Capabilities Later

Do not add a separate runtime capability service until needed.

A dynamic capability handshake becomes useful only if:

- non-Prefect runtimes need to participate,
- deployments are created and destroyed dynamically,
- multiple runtime services compete for the same catalog id,
- routing needs live health/resource negotiation beyond Prefect deployment status.
