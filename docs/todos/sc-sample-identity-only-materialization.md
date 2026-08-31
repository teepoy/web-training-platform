# TODO: Make SC Sample Storage Identity-Only

## Progress

- **Overall status:** In progress. Identity-only runtime behavior is complete;
  legacy Backfill and payload cleanup remain an explicit open decision.
- **Completed intermediate slice:** new imports write schema
  `v4_identity` (`sample_id`, `defect_id`) with an opaque UUID platform
  `sample_id` independent from the upstream `defect_id`; the sparse index keeps
  their explicit mapping for annotation-by-defect. Dataset/Collection workbench,
  map/filter, runtime, and prediction-export paths rehydrate current source
  rows; v2/v3 extras are ignored; cache keys include inspection freshness; and
  the unused direct Sample table endpoints/client have been removed.
- **Authority hardening:** source geometry is no longer persisted; map and
  reticle operations read the current Inspection. Source-derived caches use the
  required positive Inspection `change_token`. Dataset membership is sent to
  SC upstream in bounded defect-ID chunks, and the upstream database applies
  the Inspection-PK membership predicate before returning projected Arrow rows.
- **Bounded resolver:** membership is collected as streaming Polars batches,
  each batch is semi-joined with one bounded upstream request, and resolved rows
  are written incrementally to a context-owned temporary Parquet file. A
  disk-backed uniqueness index catches duplicate `defect_id` values across
  batches. Consumers must finish while the resolver context is open; cleanup is
  explicit and memory does not grow with total Dataset membership.
- **Production contract:** startup rejects adapters missing the bounded
  membership-read method. Inspection metadata without a positive
  `change_token` fails as a gRPC precondition instead of entering cache logic.
- **Final slice:** the generic sparse exporter now accepts `v4_identity`, reads
  only the two identity columns, joins annotations for scalable locator-index
  manifests, and emits deterministic patch references from Dataset-level source
  identity. Mutable source fields remain on the SC-specific export paths, which
  resolve latest upstream values and fail on source errors.
- **Verification:** identity import, latest-source projection, missing-source
  failure, provider cache freshness, Dataset/Collection runtime, prediction
  export, generic v1-v4 export, frontend unit/build, and mocked browser flows
  pass. The federated architecture graphs are valid.

This document records the proposal to give the SC Sample table one explicit
source of truth for source attributes. Persistent Dataset storage should retain
only sample membership and the stable keys needed to resolve the source row,
instead of copying the complete upstream record into S3 and later mixing that
copy with live upstream data.

Implementation is proceeding in reviewable checkpoints. The findings below
describe the pre-refactor state and remain as the migration rationale.

This todo complements
`docs/todos/stateful-upstream-simulator-and-source-automation.md`: the simulator
provides the independently owned upstream behavior, while this todo defines how
the platform stores membership and reads the latest source attributes.

## Resolved Decisions

- An imported SC Dataset is an observed membership list over the upstream
  source, not a durable historical snapshot.
- Source-owned fields always resolve to the latest upstream value. They are not
  pinned to an import-time source version.
- `source_version` is not persisted in the Dataset identity shard.
- `inspection_time` and `wafer_key` are stored once in SC Dataset metadata.
  Each persistent sample row stores only `sample_id` and `defect_id`; the full
  upstream lookup key is assembled from Dataset metadata plus the row.
- If the upstream is unavailable, source-dependent reads and operations fail
  explicitly. There is no stale full-row fallback from S3.
- Existing v2/v3 full-row shards receive temporary compatibility reading: the
  SC latest-source membership boundary projects their identity fields and
  platform overlays, and ignores extra stored source fields. Generic sparse
  storage still exposes the physical legacy rows for compatible export/readback.
- Compatibility does not make those extra fields authoritative and does not
  preserve the old mixed-source behavior.
- Existing Datasets remain readable through the compatibility adapter without
  requiring an immediate backfill; new writes use the identity-only contract.
  Whether legacy payloads should later be migrated or cleaned up remains an
  explicit open Backfill decision.
- New v4 imports generate a fresh UUID platform identity for each stored member.
  The ID is stable once persisted and is never derived from `defect_id` or another
  upstream identity. The manifest index separately maps `defect_id` back to that
  platform identity for SC writeback operations.
- A Collection job pins the Collection's current ready revision when the job is
  submitted. Membership is stable for that job, while source-owned fields are
  resolved to their latest upstream values when the job builds its input.
- Use the required positive inspection-level opaque `change_token` as the cache
  validator. It prevents a cached full projection from surviving mutable
  upstream updates; it is not Dataset versioning, historical retention, or a
  user-selectable source revision.

## Current Findings

### “Materialized data” currently means two different things

The SC path has two distinct Parquet layers:

1. **Persistent Dataset payload in object storage.** SC import streams the full
   upstream Arrow rows, adds identity columns, and writes them as sparse Parquet
   shards plus a manifest/index. New v3 imports intentionally preserve every
   upstream column.
2. **Disposable SC data-provider cache.** Before DuckDB serves a workbench
   query, `ScDataMaterializer` writes another normalized `samples_base` Parquet
   object on local/shared cache storage and joins annotation and prediction
   overlays at query time.

Relevant files:

- `apps/api/app/modules/sc/app/services/sc_import_service.py`
- `apps/api/app/modules/sc/schema.py`
- `apps/api/app/modules/storage/adapter/sparse/import_operator.py`
- `apps/api/app/modules/storage/adapter/sparse/storage.py`
- `apps/api/app/modules/storage/domain/sparse/models.py`
- `apps/api/app/modules/storage/domain/sparse/store.py`
- `apps/api/app/modules/sc/data_provider/materializer.py`
- `apps/api/app/modules/sc/data_provider/cache.py`
- `apps/api/app/modules/sc/data_provider/engine.py`
- `apps/api/app/modules/sc/data_provider/router.py`
- `docs/architecture/dataset-storage-modes.md`
- `docs/architecture/sc-data-provider-contract.md`

Calling both layers “materialization” hides which one is durable Dataset state
and which one is a rebuildable query cache. Their ownership and lifecycle must
be named separately in code and documentation.

### The persistent SC Dataset copied the complete upstream row

`_transform_upstream_batch()` requires a small core but otherwise retains the
upstream batch's complete column set. The first batch establishes the concrete
v3 schema, `_schema_columns()` records every column in the Dataset manifest, and
`SparseColumnarImportSession.append()` writes the entire table to S3-backed
Parquet shards.

The existing tests explicitly require future/dynamic upstream columns such as
`index_x` and `future_metric` to survive import:

- `apps/api/app/modules/sc/tests/test_sc_import_service.py`
- `apps/api/app/modules/sc/tests/test_sc_import_sparse_bytes.py`
- `apps/api/app/modules/storage/tests/sparse/test_materialization_schema.py`

This is the opposite of the proposed identity-only model and will require a new
source schema version rather than an in-place reinterpretation of v3.

### The Sample table changed its base source by scope

`ScDataMaterializer` currently constructs the DuckDB `samples` view differently:

- **Inspection preview:** streams complete sample rows directly from SC upstream
  and writes them into the data-provider cache.
- **Imported Dataset:** reads complete sample rows from the Dataset's S3 Parquet
  shards and writes a normalized copy into the data-provider cache.
- **Collection revision:** reads member Dataset shards for an observed revision,
  or reads a revision artifact for a materialized revision, and writes another
  normalized cache object.

In every scope, review-image metadata is fetched from the live SC upstream and
joined by `defect_id` (plus source Dataset identity for Collections). Annotation
and prediction values come from platform-owned overlays. `engine.py` exposes the
result as one DuckDB `samples` view, so the browser cannot tell which fields came
from which authority.

Relevant files and features:

- `apps/api/app/modules/sc/data_provider/materializer.py`
  - `_materialize_inspection()`
  - `_materialize_dataset()`
  - `_materialize_collection()`
  - `_load_review_images()`
  - `_normalize_dataset_base_lazyframe()`
- `apps/api/app/modules/sc/data_provider/engine.py`
  - `_samples_base`, `_review_images`, annotation and prediction joins
- `apps/api/app/modules/sc/data_provider/sample_table_descriptor.py`
- `apps/api/app/modules/sc/data_provider/router.py`
- `apps/web/src/features/sc/api/sqlWorkbenchDataSource.ts`
- `apps/web/src/features/sc/presentation/composables/useScDataWorkbench.ts`
- `apps/web/src/features/sc/presentation/components/scSampleTableColumns.ts`
- Preview, Reclassify, Collection Classify, wafer map, gallery, filters,
  selection, CSV export, and prediction-export selection

This produces a real ambiguity: an upstream coordinate or class field is live
in Preview, frozen at import time in a Dataset, and may be live or frozen for a
Collection depending on its revision path, while image counts remain live.

### The old direct sample-table endpoint is a second read path

The current web workbench uses the SQL/Arrow data provider for Preview,
Reclassify, and Collection scopes. A separate API-local inspection sample-table
path still loads and filters upstream rows in the API process:

- `apps/api/app/modules/sc/port/http/router.py`
  - `/sample-table-rows`
  - `/sample-table-rows/stream`
- `apps/api/app/modules/sc/app/services/sample_filter.py`
- `apps/web/src/features/sc/api/sampleTableDataSource.ts`

Its row mapping, filters, pagination, and identity construction overlap the SQL
provider. It should be removed after verifying there is no remaining registered
consumer, rather than becoming a fallback when the data provider or upstream is
unavailable.

### Existing consumers assumed full source columns were in Dataset storage

Reducing persistent shards to keys is not isolated to the visual table. The
following paths currently read source attributes through
`DatasetStorageAgg.list_samples()`:

- `apps/api/app/modules/sc/runtime/data_source.py`
- `apps/api/app/modules/sc/runtime/streaming_prediction.py`
- `apps/api/app/modules/sc/app/services/sc_plot_points_service.py`
- `apps/api/app/modules/sc/app/services/prediction_export_service.py`
- `apps/api/app/modules/sc/data_provider/materializer.py`
- `apps/api/app/modules/sc/sc_dataset_agg.py`
- `apps/api/app/modules/datasets/app/services/sparse_export.py`
- SC training, prediction, export, wafer map, box selection, gallery, and
  Collection composition tests

For example, the prediction image stream only needs `sample_id`,
`inspection_time`, `wafer_key`, and `defect_id` to resolve images, which already
matches the proposed minimal identity. Wafer maps, table filters, exports, and
some training views require additional upstream columns and therefore need an
explicit source-resolution adapter instead of assuming those columns are in the
physical Dataset store.

### `defect_id` is not a sufficient primary key

Current sparse imports set `sample_id` equal to `defect_id`, and the manifest
index is keyed by `sample_id`. This is only unique inside one imported Dataset.
`defect_id` is not unique across inspections and cannot identify a Collection
row by itself.

The minimum source identity is:

```text
(inspection_time, wafer_key, defect_id)
```

The platform identity remains separate:

```text
(dataset_id, sample_id)
```

The workbench `row_key` is an opaque, derived transport identity. It should not
be treated as an upstream primary key or unnecessarily persisted in source
shards. Collection rows additionally retain `source_dataset_id` and
`source_sample_id` for writeback and overlay joins.

These rules follow `CORE_DESIGNS.md` and
`docs/architecture/dataset-summary-and-collections.md`; the schema change must
not collapse platform sample identity into SC domain identity.

## Proposed Target

Use persistent SC Dataset storage as an identity/membership index, not as a
second copy of the source database:

```text
latest SC upstream state
  |-- authoritative source attributes, coordinates, bins, source metadata
  |-- review/image metadata and image resolution keys
  |
  +---- server-side projected/bulk read
                     |
                     v
identity-only Dataset membership from S3
  Dataset metadata: inspection_time + wafer_key
  sample row: sample_id + defect_id
                     |
                     v
platform overlays
  annotation + prediction + Collection row identity
                     |
                     v
disposable query/runtime view
  Sample table / map / gallery / training / prediction / export
```

The persistent identity shard is authoritative only for which samples belong to
the Dataset. SC upstream is authoritative for source-owned attributes. Platform
overlay stores are authoritative for annotations, predictions, and Dataset or
Collection membership metadata. A disposable materialized view may combine
them for a bounded purpose, but it is never another source of truth.

## Candidate Work

### P0: Approve the identity-only physical contract

Define a new SC source schema version with a deliberately closed persistent
contract:

- `sample_id` — opaque UUID platform sample identity generated for the import;
  it is persisted as the annotation/storage identity and does not depend on an
  upstream identifier.
- `defect_id` — upstream defect identity.
- Dataset metadata stores `inspection_time`, the normalized upstream inspection
  identity, and `wafer_key`, the upstream wafer identity, once per Dataset.

The identity shard does not need an opaque upstream row token. Do not persist
coordinates, bins, dynamic upstream fields, review-image counts, image URIs,
annotations, predictions, `row_key`, `map_id`, or complete source rows merely
for convenience.

`DatasetManifest.index` remains the scalable sample locator. Avoid rebuilding
the old in-memory `sample_index` map for large Datasets.

### P0: Define latest-source and availability semantics

An identity-only Dataset depends on upstream data after import. Its behavior is:

- Dataset membership remains the imported identity set.
- Every source-dependent read fetches the latest upstream values for those
  identities.
- A change to a mutable upstream field appears dynamically and does not require
  Dataset re-import or a Needs attention state.
- Upstream row versioning and historical reads are not part of this contract.
- If upstream is unavailable, source-dependent table, map, gallery, training,
  prediction, or export operations fail with a diagnosable source-unavailable
  state. They must not silently fall back to stale full rows in S3.
- A rebuildable data-provider or job cache may contain a full projection, but
  it must refresh when upstream mutable fields change. Use explicit upstream
  invalidation, a latest-change token, or an approved freshness check for cache
  coherency; this operational signal is not persisted as Dataset identity and
  does not offer historical version selection.

The freshness signal is necessary because “always latest” is otherwise defeated
by the current inspection/Dataset cache keys: a cached projection can be reused
after a mutable upstream field changes. Comparing one inspection-level token is
a bounded way to invalidate that cache without copying source versions into
every Dataset or supporting historical reads.

### P0: Add one bulk source-resolution boundary

Add an SC domain adapter that accepts an identity table or identity manifest
plus a projection and returns authoritative source columns in bulk. It should:

- resolve by `(inspection_time, wafer_key, defect_id)` against the latest
  upstream state;
- support projection so the Sample table, map, runtime, and export request only
  their required columns;
- preserve table-first Arrow/Polars streaming;
- perform a semi-join against Dataset membership so rows outside the imported
  Dataset cannot leak into a Dataset or Collection scope;
- report missing, duplicated, changed, or malformed source identities
  explicitly;
- avoid sending 100k IDs in HTTP, Prefect, or gRPC scalar parameters.

The existing Arrow Flight ticket supports column projection but not a scalable
server-side membership selector. Decide whether to add an Arrow selector
stream, a server-side temporary selection handle, or another bounded contract.
Streaming the whole inspection and semi-joining locally may be an initial
implementation only if its scale and failure semantics are explicitly
acceptable.

Relevant boundary files:

- `apps/api/app/modules/sc/domain/upstream_reader.py`
- `apps/api/app/modules/sc/adapter/grpc_upstream.py`
- `services/sc-upstream/src/sc_upstream/flight_server.py`
- `services/sc-upstream/src/sc_upstream/upstream_db.py`
- `protos/sc/v1/upstream.proto`
- generated protobuf artifacts

### P0: Rebuild the SC data-provider scope from clear authorities

Refactor `ScDataMaterializer` so Dataset and Collection scopes:

1. load only the persistent identity/membership table;
2. request the needed source projection from the upstream resolver;
3. perform an inner/semi join on the composite source key;
4. join the latest review metadata under the same freshness policy;
5. join platform annotation and prediction overlays by platform `row_key`;
6. produce one disposable `samples_base` cache for DuckDB.

Inspection Preview may continue to read directly from upstream because it has no
imported membership, but it must use the same source projection and identity
normalization. Dataset and Collection scopes must never choose between full S3
rows and upstream rows based on cache availability.

Rename cache concepts where useful so persistent Dataset payload, disposable
source-resolution view, and mutable overlays are unambiguous.

### P1: Route domain consumers through the same resolution contract

Update the consumers that currently assume `storage.list_samples()` returns the
complete SC source row:

- Sample table, filters, distinct values, selection, and CSV export.
- Wafer map, reticle calculations, box selection, and gallery.
- Training and prediction view construction.
- Prediction result export and sparse export.
- Collection observed composition and job-scoped runtime views.

Keep `DatasetStorageAgg` type-agnostic. The storage aggregate should return the
identity table and platform overlays it owns; SC source enrichment belongs in
`ScDatasetAgg` or another SC domain adapter. Do not add upstream concepts to the
generic storage Protocol.

Purpose-specific training/prediction Parquet remains allowed as a disposable
job artifact. It should be built from the identity table plus one latest source
projection, record its resolution time in job provenance, and be deleted
according to the job artifact lifecycle. It does not claim historical
reproducibility after upstream fields change.

### P1: Remove overlapping Sample table paths

- Keep the authenticated SQL/Arrow workbench provider as the single browser
  query surface for Preview, Dataset, and Collection scopes.
- Remove the API-local `/sample-table-rows` and `/sample-table-rows/stream`
  routes, their DTO mapping/filter helpers, and
  `sampleTableDataSource.ts` after confirming there are no remaining consumers.
- Keep one descriptor/column-discovery policy. With identity-only Dataset
  storage, dynamic upstream columns must come from the source projection schema,
  not from whichever S3 shard version happens to be present.
- Do not retain the old route as a fallback.

### P1: Keep existing v2/v3 Datasets readable without backfill

- Introduce a new schema version for identity-only storage.
- Read v2/v3 Datasets through a temporary compatibility adapter that projects
  `sample_id` and `defect_id` from their existing shards, derives/validates the
  Dataset-level `inspection_time` and `wafer_key`, and ignores all extra source
  columns.
- Apply this authority rule at the SC latest-source membership boundary; do not
  make generic sparse storage import SC policy or reinterpret its physical rows.
- Enrich those projected identities from the latest upstream source, exactly as
  for new identity-only Datasets.
- Do not relabel existing full-row shards as identity-only.
- Do not rewrite historical IDs or stored shards. Their old platform identity
  remains stable, while bulk SC membership reads hide copied source extras.

### P1: Update tests around authority, not duplicated values

Replace “all future upstream fields survive import” assertions with contracts
that prove:

1. import persists only the approved identity columns and locator index;
2. Dataset membership excludes upstream rows not present in the identity shard;
3. Preview and Dataset resolve the same latest source attribute values;
4. mutable upstream fields appear after cache invalidation without re-import;
5. upstream outage never activates an S3 full-row fallback;
6. annotation and prediction overlays remain available only when source
   resolution succeeds under the approved policy;
7. duplicate `defect_id` values across inspections and Collections remain
   distinct through composite source identity and `row_key`;
8. projection pushdown avoids fetching unused source columns;
9. training/prediction job artifacts record their source-resolution time;
10. v2/v3 compatibility projects identity and ignores extra fields
    deterministically.

## Explicit Non-Candidates

- Image bytes should continue to resolve through the image-parser data plane;
  they do not belong in the identity shard.
- Annotation and prediction overlays remain platform-owned and must not be
  written back into upstream source rows.
- Platform metadata such as label space and connector/import receipt belongs in
  the appropriate Dataset/receipt contract. Source-owned geometry is resolved
  from the current upstream Inspection and is not persisted in Dataset metadata
  or repeated on identity rows.
- `defect_id` alone must not become a global primary key or Collection row key.
- The browser must not join upstream and S3 data itself.
- The API must not query the upstream database directly; it continues through
  the generated gRPC/Arrow boundary.
- A cached disposable full projection is acceptable for query performance, but
  it must be versioned, rebuildable, and clearly non-authoritative.
- Full historical source archival is a separate product/storage decision, not
  an implicit exception to identity-only Dataset storage.

## Proposed Execution Order

1. Add the Dataset-level inspection identity fields and the two-column sample
   identity shard contract.
2. Define the upstream cache-invalidation/freshness signal needed to serve the
   latest mutable fields without historical versioning.
3. Design the projected bulk source-resolution/selection protocol and measure it
   at representative inspection sizes.
4. Add the new identity-only SC schema version and importer tests.
5. Refactor the SC data provider to join membership, source projection, review
   metadata, and platform overlays under one version policy.
6. Route map, gallery, selection, export, training, and prediction through the
   same SC domain resolution boundary.
7. Update Collection observed/runtime composition and provenance.
8. Remove the overlapping API-local Sample table path.
9. Add v2/v3 compatibility or re-import tooling, then migrate development
   fixtures first.
10. Update architecture and operator documentation and run full storage,
    provider, frontend, runtime, and Compose verification.

## Acceptance Criteria

- A new SC Dataset's persistent sample shards contain only the approved identity
  columns and scalable locator/index metadata.
- The Sample table has a documented authority for every column: upstream source,
  Dataset membership, annotation overlay, prediction overlay, or derived view
  value.
- Preview, Dataset, and Collection scopes use one source-resolution policy and
  never change authority because a cache or S3 copy is available.
- Dataset and Collection queries cannot expose upstream rows outside their
  persisted membership.
- Mutable source fields refresh to their latest values, and upstream outages
  produce explicit errors; no stale full-row fallback exists.
- Composite SC identity and platform `row_key` remain correct when `defect_id`
  repeats across inspections or member Datasets.
- Training, prediction, export, map, gallery, filters, and annotations still work
  through explicit projected views.
- Disposable query/job Parquet is freshness-tracked and rebuildable and is not
  described as Dataset source truth.
- Existing v2/v3 full-row Datasets have a tested compatibility reader that
  ignores extra fields and resolves latest source values.
- The obsolete direct Sample table route and client are removed after consumer
  verification.
- Relevant API, service, frontend, migration, performance, and end-to-end tests
  pass after implementation.

## Before Implementation

The identity layout, observed-membership, always-latest,
fail-when-upstream-unavailable, cache-freshness, pinned Collection job revision,
and temporary v2/v3 compatibility semantics are approved. Compatibility reads
preserve existing behavior without an immediate backfill; the separate legacy
Backfill/cleanup decision remains open.
