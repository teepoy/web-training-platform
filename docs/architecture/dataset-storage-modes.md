# Dataset Storage Modes

> **Current state.** Sparse-native import, list, annotate, train, predict, and export are implemented. Capabilities that remain deferred or intentionally unsupported are documented in the matrix below. See [Future Directions](#future-directions) for the remaining deferred scope.

Every dataset in the platform falls into one of two storage modes: `db_full` or `file_shard_sparse`. This document defines the boundaries between them, enumerates which operations are supported, unsupported, or deferred, and preserves the core intent behind allowing large datasets to diverge from small-dataset workflows.

The current storage refactor standardizes both modes behind `DatasetStorageAgg`, opened through `DatasetStorageFactory.open(dataset_id, org_id)`. Runtime/domain code no longer selects `SampleAccessFactory`, `DatasetSampleService`, `RuntimeMaterializer`, or raw storage operators to read training/prediction data.

---

## Intent Origin

> **Start from intent, not from parity pressure.**
>
> The goal is **not** to rebuild full `SampleORM + Label Studio` parity for 100k+ datasets.
> The goal is to support the real large-dataset workflow:
>
> - batch ingest into platform-owned shard storage
> - run prediction/reclassification at scale
> - allow sparse human correction where useful
> - avoid full LS task creation and avoid stuffing every sample into the DB
>
> Any implementation step that drifts toward "make big datasets behave exactly like small datasets" should be treated as a regression against intent unless explicitly justified.

This section lives above the fold on purpose. The sparse mode is a deliberate, scoped design choice, not a temporary gap that needs closing. Every capability decision below flows from this intent.

---

## Storage Modes

### `db_full`

The standard storage mode for small and medium sized datasets. Every sample is persisted as a full `SampleORM` row in the database. Every dataset has a corresponding Label Studio project, and annotation workflows flow through LS tasks. Sample browsing, pagination, individual annotation, prediction review, training, and export all operate over materialized sample rows.

This is the current platform default and the only mode that existed before `file_shard_sparse` was introduced.

### `file_shard_sparse`

A storage mode for large datasets (100k+ samples) where materializing every sample as a database row is impractical. Samples live in platform-owned parquet shard files, not in `SampleORM` rows. Only dataset-level metadata and shard manifest information is stored in the database.

This mode intentionally skips Label Studio integration. There is no LS project, no LS tasks, and no LS annotation sync. The primary interaction surface is batch prediction at scale followed by sparse human correction on prediction outputs, not full-sample browsing and individual annotation.

Sparse mode is **opt-in only**. No existing dataset is converted to sparse automatically.

---

## Capability Matrix

| Capability                                   | `db_full` | `file_shard_sparse` | Notes                                                                                                                                                                                                                                                                                                                        |
| -------------------------------------------- | --------- | ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Dataset create                               | Supported | Supported           | Sparse creation skips LS project setup and full sample materialization. Only dataset metadata and shard manifest are registered.                                                                                                                                                                                             |
| Import (Parquet shards)                      | Supported | Supported           | Primary sparse ingest path. Streams defects into Parquet shards (10k rows each), builds manifest with `sample_index` for O(1) `defect_id` resolution. v2 importer embeds image bytes in a `list<struct>` column (see [v2 Embedded Image Storage](#v2-embedded-image-storage)). For `db_full`, materializes `SampleORM` rows. |
| List (paginated, 100k+)                      | Supported | Supported           | Sparse datasets expose shard-level summaries and manifest-driven pagination. Full `SampleORM` pagination is not available.                                                                                                                                                                                                   |
| Sample browsing / individual materialization | Supported | Unsupported         | Samples live in Parquet shard files, not `SampleORM` rows. Per-sample materialization is not available.                                                                                                                                                                                                                      |
| Annotation (bulk)                            | Supported | Supported           | Sparse bulk annotation resolves `defect_id` → `sample_id` via `manifest.sample_index` at O(1) per annotation. `sample_id` equals `defect_id` in sparse mode (no FK constraint).                                                                                                                                              |
| Annotation (individual)                      | Supported | Unsupported         | No individual `SampleORM` rows to anchor annotations against. Sparse correction is done through prediction review.                                                                                                                                                                                                           |
| Label Studio project / task integration      | Supported | Unsupported         | Sparse datasets do not create an LS project. This is intentional, not a missing feature.                                                                                                                                                                                                                                     |
| LS annotation sync                           | Supported | Unsupported         | No LS project means no sync surface.                                                                                                                                                                                                                                                                                         |
| Prediction (batch)                           | Supported | Supported           | Streaming shard-based prediction with 256-row model batches. Dataset workers decode and preprocess paired images; per-shard prediction Parquet output and a lightweight `job_result.json` manifest persist results.                                                                                                          |
| Prediction result readback / pagination      | Supported | Supported           | Offset/limit pagination via `job_result.json` manifest. Reads only the needed shard(s) and Parquet rows.                                                                                                                                                                                                                     |
| Prediction collection LS sync                | Supported | Unsupported         | No LS project to sync prediction collections into.                                                                                                                                                                                                                                                                           |
| Training                                     | Supported | Supported           | `yolo-sc-v1` trainer, 50 epochs. Paired grayscale patch images become a two-channel `128x128` tensor in DataLoader workers. Zero-annotation datasets fail with a clear error.                                                                                                                                                |
| Export (with predictions)                    | Supported | Supported           | Generic `sparse-export-v1` JSON remains available. SC sparse Datasets also expose current-result KLARF 1.2/1.8, Parquet, and ZIP package exports with optional server-side Annotation Sampling.                                                                                                                              |
| Feature extraction                           | Supported | Deferred            | Requires sparse-native feature storage design.                                                                                                                                                                                                                                                                               |
| Similarity search                            | Supported | Unsupported         | Depends on per-sample vectors not available for sparse datasets.                                                                                                                                                                                                                                                             |
| Random sampling                              | Supported | Unsupported         | No per-sample materialization to sample from.                                                                                                                                                                                                                                                                                |
| Wafer points                                 | Supported | Unsupported         | Wafer coordinate data lives on individual `SampleORM` rows and has no sparse equivalent.                                                                                                                                                                                                                                     |
| Selection metrics                            | Supported | Limited             | Shard-level aggregate metadata is available. Per-sample selection statistics are not.                                                                                                                                                                                                                                        |
| Uncovered clusters                           | Supported | Deferred            | Cluster analysis depends on feature extraction and sample-level vectors.                                                                                                                                                                                                                                                     |
| Image upload                                 | Supported | Unsupported         | Individual image upload creates `SampleORM` rows. Sparse ingest is batch-oriented.                                                                                                                                                                                                                                           |
| Agent chat                                   | Supported | Supported           | The global agent can query dataset-level metadata for both modes. Sample-level agent operations are unavailable for sparse datasets.                                                                                                                                                                                         |
| Dataset delete                               | Supported | Supported           | Sparse delete cleans shard artifacts deterministically using dataset-owned prefixes. No per-image enumeration needed. LS project deletion is skipped.                                                                                                                                                                        |
| Runtime materialization                      | Deferred  | Deferred            | Training and prediction no longer call the HTTP materialization endpoint. They consume `DatasetStorageAgg.list_samples(return_lazyframe=True, ...)` and perform any local parquet/HF conversion inside the trainer/predictor runtime.                                                                                        |

---

## DatasetStorageAgg and DatasetAgg

`DatasetStorageAgg` is the storage-mode aggregate Protocol for a single dataset. It owns storage-level behavior across `db_full` and `file_shard_sparse`:

- `list_samples(...)`, including `return_lazyframe=True`, `with_labels=True`, `sample_ids`, pagination, and filter arguments.
- `write_samples(...)` for generic bulk ingest streams such as SC import rows.
- Annotation persistence and readback (`create_annotations`, `update_annotations`, `list_annotations`, stats/recent annotations).
- Prediction result persistence/readback and feature/search operations where the backend supports them.
- Storage-level delete and optional materialize/as-HF helper methods.

`DatasetStorageFactory.open(dataset_id, org_id)` is the only supported dispatcher from dataset metadata to concrete storage implementation. The caller does not branch on `storage_mode` and does not instantiate sparse/db-full storage classes directly.

`DatasetStorageAgg` deliberately does **not** own view projection or domain mapping. It can return raw storage rows or a Polars `LazyFrame`; trainer/predictor/domain code is responsible for choosing the view contract and transforming rows into its local runtime shape.

`DatasetAgg` is the domain specialization layer that wraps a `DatasetStorageAgg`. For SC this is `ScDatasetAgg`, which owns wafer-domain behavior such as:

- wafer/die/reticle point computation from storage columns or metadata
- bulk SC annotation semantics (`defect_id` → storage `sample_id`)
- domain-level prediction orchestration helpers

The separation is intentional: storage implementations remain type-agnostic; SC-specific coordinate, defect, and wafer semantics do not leak into the generic storage Protocol.

### Replaced Legacy Infrastructure

The following layers were removed from training/prediction/read paths and must not be reintroduced as fallback mechanisms:

- `RuntimeMaterializer`
- `BulkViewLoader`
- `SampleBulkDataset`
- `DatasetSampleService`
- `SampleAccessFactory`, `DbFullSampleAccess`, and sparse sample-access variants
- `PredictionRepository.get_sample()` as a prediction-flow sample fetch fallback

If a new read/write capability is needed, extend `DatasetStorageAgg` or the owning domain `DatasetAgg` explicitly. Do not silently bypass the aggregate through raw repositories or ad-hoc shard readers.

---

## Runtime Materialization

Runtime materialization is no longer the training/prediction data path. It remains a storage-level concept for explicit future/diagnostic conversion, not a required runtime cache.

**Key properties:**

- **Derived artifact, not source of truth.** A materialized parquet snapshot, if produced, is derived from storage. Source data (Parquet shards, object storage, database records) remains authoritative.
- **Not a trainer/predictor dependency.** Workers open `DatasetStorageAgg` and request `list_samples(return_lazyframe=True, ...)`. Training can write local temporary parquet and open it with HuggingFace datasets; prediction streams the LazyFrame directly.
- **No storage-layer mapper.** View projection is not performed by `DatasetStorageAgg.materialize()`. Mappers and view-specific transforms belong to the trainer/predictor/domain layer.

Workers must not call the materialization endpoint before compute begins. Failure to materialize must not block training or prediction because the runtime path is the storage aggregate LazyFrame path.

---

## SC (Patch) Sparse Path

`file_shard_sparse` is the default storage mode for SC (patch wafer inspection) datasets. The SC sparse path operates end-to-end as follows:

**Import.** SC Import as Dataset uses the API service direct sparse import path. It reads upstream defect rows, normalizes them into sparse SC rows with image metadata references, writes Parquet shards, and publishes the sparse manifest / `sample_index`. It does not materialize image bytes during import and no longer registers a Prefect `sc_import` deployment.

**List.** Sparse datasets expose shard-level summaries and manifest-driven pagination. The manifest's `total_rows` and `shards[]` metadata drive list views for datasets of 100k+ rows.

**Annotate.** Bulk annotations resolve `defect_id` → `sample_id` through `ScDatasetAgg`. Sparse mode uses the storage aggregate's manifest index, while `db_full` performs one JSON-metadata query. The `sample_id` equals the `defect_id` in sparse mode (no `SampleORM` rows exist); unknown defect IDs are excluded.

**Train.** `train_job` opens the dataset through `DatasetStorageFactory`, then calls `storage.list_samples(with_labels=True, return_lazyframe=True)`. External runtimes consume the data-plane manifest. The API-local Ultralytics module owns materialization and its temporary workspace. `libs/ml` opens the resulting Parquet paths as an algorithm-owned streaming Dataset; each DataLoader worker decodes the defective/template images as grayscale, resizes both to `128x128`, and stacks them in channel order. Training runs for 50 epochs without building a local image-folder copy. The checkpoint remains a local path until `ArtifactOutput` consumption uploads it. No legacy `RuntimeMaterializer`, `BulkViewLoader`, or `DatasetSampleService` is used.

**Predict.** `predict_job` opens the dataset through `DatasetStorageFactory`, then calls `storage.list_samples(return_lazyframe=True, sample_ids=...)`. The Ultralytics module materializes bounded Parquet and downloads its checkpoint to its own temporary directory. A four-worker prediction DataLoader performs Parquet reads, grayscale decode, `128x128` resize, and two-channel stack; the GPU-facing model loop consumes collated batches of 256. Only the storage write path is shared. Predicting the full dataset should pass `sample_ids=None`; sending 100k IDs through Prefect parameters exceeds Prefect's serialized-parameter limit.

**Export.** The `SparseExportAssembler` joins shard rows with annotations and prediction results, producing `sparse-export-v1` format output. Annotations are resolved via `sample_id IN (manifest.sample_index keys)` (batched at 500). Prediction results are joined by `(shard_index, row_index)` from the latest completed prediction job's per-shard Parquet output.

### Unsupported SC Capabilities (Intentional)

These capabilities are explicitly NOT supported for sparse SC datasets. The design intentionally diverges from `db_full` parity:

- **Label Studio sync.** No LS project is created for sparse datasets. LS task creation, annotation sync, and prediction collection sync are not available.
- **Similarity search.** Depends on per-sample embedding vectors not available for sparse storage.
- **Random sampling.** No per-sample materialization exists to draw random samples from. The sparse interaction model is prediction review, not exploratory browsing.
- **Per-sample materialization.** Individual `SampleORM` rows are never created for sparse datasets. All sample data lives in Parquet shards.

### SC source schema v3 and v2 compatibility

SC sparse datasets have versioned source data models that share the same
`file_shard_sparse` storage mode.

**Storage model (v3 shards).** All new imports preserve the full upstream Arrow
schema in Parquet, add the required platform identity columns, and record the
complete concrete column list and Arrow type strings in
`DatasetManifest.schema_columns`. The importer does not construct embedded
patch-image structs. Patch and review images resolve on demand from inspection,
wafer, defect, image-role, and review-image identity. If an upstream metadata
column collides with a workbench-computed column, the SQL `samples` view exposes
the source value as `upstream_<name>` and keeps the computed name for current
workbench semantics; for example, `upstream_images` is the source count and
`images` is the live review-image count.

The SC data viewer discovers this concrete list from the SQL data provider with
`SELECT * FROM samples LIMIT 0`. Known fields retain their curated labels and
filter behavior; additional scalar fields receive generic viewer columns, while
nested/binary values remain visible without unsafe filter controls.

**Upstream model.** When SC wafers are scanned by inspection equipment, each defect record carries image _references_ in the form of lightweight URIs (S3 keys, file paths). These URIs point to image files stored in the upstream wafer database or object storage. The upstream system never ships raw bytes directly into defect records.

**Storage model (v2 shards).** SC v2 shards use a single `images` column of type `list<struct>` instead of the legacy `image_uris` and `metadata` JSON string columns. Image bytes should be embedded during ingest when they are available; `bytes` remains nullable so a row can retain an explicit upstream reference for runtime batch resolution. Each image struct carries:

| Field          | Type              | Purpose                                                         |
| -------------- | ----------------- | --------------------------------------------------------------- |
| `image_id`     | string            | Unique per-sample identifier                                    |
| `image_type`   | string            | Image category (e.g. `REVIEW_HIGH_MAG`)                         |
| `role`         | string            | Semantic role: `review`, `patch_template`, or `patch_defective` |
| `content_type` | string            | MIME type (e.g. `image/jpeg`)                                   |
| `filename`     | string            | Original filename                                               |
| `bytes`        | binary            | Raw image bytes                                                 |
| `source_uri`   | string (nullable) | Optional upstream provenance URI                                |

Training and prediction normalize both storage modes to the same two-role SC input contract: `patch_template` and `patch_defective`. Resolution order is:

1. embedded `images[].bytes` from Arrow/Parquet;
2. a `data:image/*;base64,...` URI (used by deterministic dev seeds);
3. an `s3://` or `memory://` object URI through artifact storage;
4. an explicit SC upstream reference containing inspection, wafer, defect, and image-type identity.

Roles must be declared in `images[].role` or `metadata.shard_images[].role`.
The runtime does not infer roles from `image_uris` position, `image_type`, or review
images; missing role metadata is a dataset validation failure.

The durable training workflow runs a preflight that validates the selected
annotations and requires at least two declared labels. The HTTP submission path does
not open sample storage or raw Parquet. Preflight does not resolve image bytes; image
availability belongs to the SC runtime. Both current trainers skip rows without two
readable image roles and raise `RuntimeExecutionError` if fewer than two effective
labels remain after that filter. The optional detailed readiness report may still
expose readable, runtime-resolvable, unusable, and skipped counts; there is no
configurable `missing_image_policy`.

For SC Train & Predict, the workflow applies the user-visible training policy after
the workflow filter: labeled rows are ordered by stable sample identity and at most
1,000 rows per class enter training materialization. The prediction stage keeps the
original workflow scope, so rows held out by the training cap still receive platform
predictions for validation/review.

API-local compatibility materialization writes Parquet in bounded row batches and
exposes a re-iterable Parquet row view; it does not create a second Hugging Face cache.
Compatibility predictors consume that row view in fixed-size inference batches rather
than converting the complete validation scope to a Python list.
Use the reproducible benchmark below when changing this path:

```bash
PYTHONPATH=apps/api .venv/bin/python \
  apps/api/scripts/benchmark_sc_materialization.py \
  --rows 5000 --classes 5 --unique-images 1000 --image-size 64
```

**Schema version gating.** `DatasetManifest.schema_version` distinguishes v3,
v2, and legacy source rows. Current imports carry `schema_version="v3"`; v2
datasets retain the embedded `images` list; legacy datasets have `None` or
`"v1"` and use the old `image_uris` + `metadata` columns.

V2 remains an explicit read compatibility path. The v2 image endpoint reads the
embedded list with column projection; v3 image access derives on-demand refs
from scalar identity. Legacy URI-only behavior remains limited to legacy-aware
readers and is not a fallback for a versioned v2 or v3 manifest.

**Image serving.** Individual images embedded in v2 shards are available through a dedicated endpoint that reads the `images` column only (column projection), matches the requested `image_id`, and returns raw bytes with the correct `Content-Type` header:

```
GET /api/v1/datasets/{dataset_id}/samples/{sample_id}/images/{image_id}
```

Response headers include `Content-Disposition: inline` with the original filename and `Cache-Control: public, max-age=1200` (20-minute browser cache). The endpoint intentionally does not expose `source_uri` fields to clients.

Because this endpoint is consumed by browser-native image elements (`<img>`, virtualized blink tables, and preview grids), clients cannot rely on request headers for auth or organization context. Frontend image URLs must therefore include the same auth context as query parameters (`token` and, when applicable, `org_id`). Use the shared frontend URL helpers instead of hand-building image paths:

- Dataset/storage URIs (`s3://`, `memory://`) go through `resolveImageUri()` / `resolveImageUris()` in `apps/web/src/shared/utils/image-adapters.ts`, which proxies them through `/api/v1/images/resolve?...` and appends auth query parameters.
- SC upstream-style images use `scPatchUrl()`, `scReviewUrl()`, or `buildScBlinkImageUrls()` in `apps/web/src/features/sc/domain/models.ts`. The lower-level `patchImageUrl()` and `reviewImageUrl()` helpers intentionally return raw paths and must not be used directly as `<img src>` values.
- Imported SC dataset views should prefer dataset-owned image refs (`/api/v1/datasets/{dataset_id}/samples/{sample_id}/images/{image_id}`) over upstream inspection paths. Upstream `/api/v1/sc/images/...` remains a compatibility/preview endpoint, not the preferred imported-dataset rendering path.

### Smoke Command

```bash
# Run all smoke tests (requires: make up-dev)
make smoke-tests

# Run just the wafer e2e smoke
uv run python scripts/smoke_wafer_e2e.py

# Run db-full seed images through combined train-and-predict
make smoke-wafer-train-predict

# With config overrides
uv run python scripts/smoke_wafer_e2e.py --import-max-rows 1000 --trainer-id yolo-sc-v1
```

Requires the compose stack to be running (`make up-dev`). The smoke script creates a sparse SC dataset from the local wafer SQLite database through the API direct import path, validates that patch/review view rows expose image refs, performs an actual image proxy GET for an embedded image, runs training with `yolo-sc-v1`, runs full-dataset prediction with `sample_ids=None`, and verifies export contains predictions.

---

## Migration & Defaults

All existing datasets remain `db_full`. An Alembic migration sets `storage_mode = 'db_full'` as the default for existing rows and any future rows that don't explicitly opt in.

Sparse mode is strictly opt-in. No dataset is converted to sparse unless an operator explicitly creates it as `file_shard_sparse`. Seed scripts, test fixtures, and local dev flows continue to produce `db_full` datasets by default.

The `storage_mode` field is orthogonal to `dataset_type`. Classification and SC datasets can each use the storage modes explicitly supported by their capability declarations. Storage behavior is never inferred from the semantic type.

---

## Future Directions

The following sparse-native capabilities remain deferred. They are listed here to make the deferred scope explicit so future engineers don't mistake their absence for an oversight:

- **Sparse-native feature extraction and similarity search.** These depend on per-sample vector storage that doesn't exist yet for sparse datasets. Embedding-based search, uncovered cluster analysis, and feature ops require this foundation.
- **Full sample browsing for sparse datasets.** Emulating `SampleORM` pagination over shard files is explicitly out of scope. The sparse interaction model is prediction review, not exhaustive browsing.
- **Random sampling.** No per-sample materialization exists to support random draws from the dataset.

Previously deferred capabilities that are now implemented:

- **Sparse-native import** (T5-T6): streaming defect → Parquet shard + manifest import.
- **Sparse-native bulk annotation** (T7-T8): `manifest.sample_index`-based `defect_id` → `sample_id` resolution.
- **Sparse-native training** (T10-T12): `yolo-sc-v1` with paired grayscale Dataset preprocessing and metric events.
- **Sparse-native prediction** (T13-T17): streaming batch prediction, result readback with offset/limit pagination.
- **Sparse-native export** (T18-T19): `sparse-export-v1` with annotation and prediction joins.
