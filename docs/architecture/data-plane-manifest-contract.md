# Data Plane Manifest Contract

Status: draft
Date: 2026-06-18

This contract defines the first data-plane manifest shape for trainer, predictor, and materializer runtime execution.

## Goals

- Keep runtime inputs table-first and bulk-oriented.
- Make Arrow/Polars schema the source of truth for tabular data.
- Avoid row DTO lists as a transport or materialization strategy.
- Support both object-store manifests and Arrow Flight streaming.
- Keep temporary materialized data job-scoped with explicit cleanup.

## Data Model

The data-plane unit is a **table view**.

In process:

- prefer Polars `LazyFrame` near data loading,
- allow Polars `DataFrame` or Arrow `Table` near consumers,
- use Arrow/Polars schema objects for columns and types.

Across process boundaries:

- pass a manifest/ref, not a Python `LazyFrame`,
- encode tabular payloads as Parquet/Arrow shards or Arrow Flight streams,
- keep schema in Arrow-compatible form.

## Single Source Of Truth

Arrow/Polars schema is the source of truth for table columns.

Preferred code-first shape:

```python
import pyarrow as pa

SC_PATCH_IMAGE_V1_SCHEMA = pa.schema([
    pa.field("sample_id", pa.string(), nullable=False),
    pa.field("defect_id", pa.string(), nullable=False),
    pa.field("inspection_time", pa.string(), nullable=False),
    pa.field("wafer_key", pa.int64(), nullable=False),
    pa.field("wafer_x", pa.int64(), nullable=False),
    pa.field("wafer_y", pa.int64(), nullable=False),
    pa.field("rough_bin", pa.int64(), nullable=False),
    pa.field("class_number", pa.int64(), nullable=True),
    pa.field("test_id", pa.int64(), nullable=True),
    pa.field("label", pa.string(), nullable=True),
    pa.field("patch_template_bytes", pa.binary(), nullable=True),
    pa.field("patch_defective_bytes", pa.binary(), nullable=True),
])
```

Polars consumers derive or validate against the same logical schema. If cross-language code generation becomes necessary, add protobuf for manifest metadata, but do not replace Arrow schema as the table schema truth.

## Manifest Shape

The manifest is metadata around one or more table transports.

```json
{
  "manifest_schema_version": "data-plane-manifest.v1",
  "view_contract": "sc.patch_image.v1",
  "view_schema_version": "1",
  "dataset_id": "ds_123",
  "job_id": "job_123",
  "format": "parquet",
  "schema_ref": "arrow-schema://sc.patch_image.v1/1",
  "row_count": 100000,
  "columns": [
    { "name": "sample_id", "arrow_type": "string", "nullable": false },
    { "name": "patch_defective_bytes", "arrow_type": "binary", "nullable": true }
  ],
  "image_encoding": "embedded_bytes",
  "image_roles": ["patch_template", "patch_defective"],
  "label_columns": ["label"],
  "shards": [
    {
      "uri": "s3://bucket/jobs/job_123/input/shard-000.parquet",
      "format": "parquet",
      "row_count": 4096,
      "size_bytes": 12345678
    }
  ],
  "flight": null,
  "auth": {
    "mode": "job_scoped",
    "audience": "runtime-service"
  },
  "ttl_seconds": 86400
}
```

For Arrow Flight:

```json
{
  "format": "arrow_flight",
  "flight": {
    "endpoint": "grpc://sc-upstream:9093",
    "ticket": "opaque-job-scoped-ticket",
    "stream_schema_ref": "arrow-schema://sc.patch_image.v1/1"
  },
  "shards": []
}
```

## Image Payload Policy

Training inputs should include image bytes in the table or materialized shards when practical. This makes training deterministic and avoids runtime DataLoader workers sharing upstream gRPC channels.

Prediction may choose either:

- `embedded_bytes`: materialized image bytes in Parquet/Arrow shards,
- `signed_refs`: table columns contain signed image refs,
- `arrow_flight`: runtime reads an Arrow IPC stream that includes bytes or refs.

If prediction uses refs or Arrow Flight, the predict flow/data-plane adapter must provide the missing-data completion path and local Arrow table/shard writing when the model/DataLoader requires local tabular input.

## Row Loops

Python row loops over samples are forbidden on the main data path.

Allowed exceptions:

- manifest shard lists,
- tiny metadata collections,
- label map construction for bounded label sets,
- bounded batch adapters with explicit batch size,
- image decode/preprocess inside `torch.utils.data.Dataset` / `DataLoader` workers.

Preprocess should be moved out of the main orchestration loop and into DataLoader/Dataset batch execution whenever possible.

## Materializer

Materializer is a data-plane capability in its own API module. It may use storage ports but should not depend on storage implementation classes.

Responsibilities:

- resolve a table view,
- bulk/batch fetch or embed required images,
- write Parquet/Arrow shards or expose Arrow Flight,
- return a manifest,
- register job-scoped cleanup metadata.

The materializer does not return Python row lists or service-local dataset objects as its public output.

## Auth

Runtime services use service credentials plus job-scoped authorization.

Do not pass long-lived user tokens through Prefect parameters.

The API creates or authorizes job-scoped access for:

- manifest reads,
- object-store refs,
- Arrow Flight tickets,
- prediction/artifact writeback.

## Lifecycle And Cleanup

First version uses job-scoped temporary manifests and shards.

- Materialized data has TTL.
- Successful jobs may clean up eagerly when no downstream consumer needs the data.
- Failed/cancelled jobs should clean up in finalizers where possible.
- A background cleanup job should remove expired manifests/shards.

Reusable materialization cache is out of scope for the first version.

## Error Semantics

V1 policy:

- train: fail fast on data-plane preparation failure or required image/schema failure,
- predict: allow partial completion if the runtime can continue,
- missing images: each image-bearing route must explicitly choose `fail` or
  `skip`; there is no implicit default,
- skipped samples produce no prediction result,
- all partial failures must be represented in an error table or job error manifest.

Required counters:

- `input_rows`
- `processed_rows`
- `skipped_rows`
- `failed_rows`
- `output_rows`

## Prediction Writeback

Prediction writeback is table-first.

Preferred path:

1. Runtime writes prediction Parquet/Arrow shards.
2. Runtime reports a prediction manifest.
3. API commits predictions through storage/data-plane writeback.

Add gRPC streaming writeback as an option for lower-latency or smaller prediction jobs. The streaming option must still be batch/table-oriented, not one request per prediction row.

## Artifact Contract

Model artifacts use two contracts at different layers:

- `model.bundle.v1` is the transport envelope for files and provenance;
- a versioned algorithm-specific model contract, such as
  `sc.yolo.model.v1`, defines trainer/predictor compatibility.

The training route output contract and persisted model metadata use the
algorithm-specific contract. A predictor must consume the exact same contract
and schema version.

Minimum bundle manifest:

```json
{
  "artifact_contract": "model.bundle.v1",
  "model_contract": "sc.yolo.model.v1",
  "model_schema_version": "1",
  "artifact_id": "artifact_123",
  "job_id": "job_123",
  "algo_id": "yolo-sc",
  "algo_version": "1",
  "train_flow_version": "2026.06.18",
  "code_version": "git-sha-or-image-digest",
  "files": [
    { "role": "checkpoint", "uri": "s3://.../model.pt" },
    { "role": "labels", "uri": "s3://.../labels.json" },
    { "role": "preprocess", "uri": "s3://.../preprocess.json" }
  ],
  "predictor_compatibility": ["yolo-sc-v1"]
}
```

Train and predict jobs must persist enough provenance to reconstruct:

- Prefect deployment name,
- Prefect deployment version if available,
- runtime image digest or code version,
- algo id and algo version,
- catalog id and catalog version.

## View And Manifest Coupling

View contract code owns semantic projection: what columns mean and which columns are required.

Manifest contract code owns transport metadata: where the table lives, how it is encoded, auth, TTL, and shard/stream refs.

Coupling lives in data-plane adapter code that validates a manifest against the requested view contract and Arrow schema. Do not spread this coupling across trainer/predictor implementations.
