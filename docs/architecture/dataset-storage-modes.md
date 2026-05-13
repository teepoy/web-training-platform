# Dataset Storage Modes

> **This document reflects Phase 1 capabilities.** Sparse-native prediction/review is in active development. Training/export/feature-ops parity is explicitly deferred to Phase 2. See [Future Directions](#future-directions) for the deferred scope.

Every dataset in the platform falls into one of two storage modes: `db_full` or `file_shard_sparse`. This document defines the boundaries between them, enumerates which operations are supported, unsupported, or deferred, and preserves the core intent behind allowing large datasets to diverge from small-dataset workflows.

---

## Intent Origin

> **Start from intent, not from parity pressure.**
>
> The goal is **not** to rebuild full `SampleORM + Label Studio` parity for 100k+ datasets.
> The goal is to support the real large-dataset workflow:
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

| Capability | `db_full` | `file_shard_sparse` | Notes |
|---|---|---|---|
| Dataset create | Supported | Supported | Sparse creation skips LS project setup and full sample materialization. Only dataset metadata and shard manifest are registered. |
| Sample browsing / pagination | Supported | Limited | Sparse datasets expose shard-level summaries and sampled metadata. Full `SampleORM` pagination is not available; the `/samples-with-labels` pattern does not apply. |
| Annotation (individual) | Supported | Unsupported | No LS tasks, no individual `SampleORM` rows to anchor annotations against. |
| Annotation (bulk) | Supported | Unsupported | Same as above. Sparse correction is done through prediction review, not bulk annotation. |
| Label Studio project / task integration | Supported | Unsupported | Sparse datasets do not create an LS project. This is intentional, not a missing feature. |
| LS annotation sync | Supported | Unsupported | No LS project means no sync surface. |
| Prediction (batch) | Supported | Supported | Sparse prediction reads directly from shard payloads rather than iterating `SampleORM` rows. |
| Prediction (single) | Supported | Limited | Resolvable through shard lookup but not via the individual `sample_id` prediction path used by `db_full`. |
| Prediction review / reclassify | Supported | Limited | Sparse review actions can be created, but saving annotation versions back is deferred (requires `SampleORM`-backed annotations). LS is not involved. |
| Prediction collection LS sync | Supported | Unsupported | No LS project to sync prediction collections into. |
| Training | Supported | Deferred | Training flows currently assume full `SampleORM` enumeration. Sparse-native training is a Phase 2 concern. |
| Export (parquet) | Supported | Deferred | Export assumes `SampleORM`-backed row iteration. Sparse-native export is deferred to Phase 2. |
| Feature extraction | Supported | Deferred | Feature ops require sample-level access that sparse mode does not provide in Phase 1. |
| Similarity search | Supported | Deferred | Embedding-based search depends on per-sample vectors. Deferred until sparse-native feature storage is designed. |
| Wafer points | Supported | Unsupported | Wafer coordinate data lives on individual `SampleORM` rows and has no sparse equivalent. |
| Selection metrics | Supported | Limited | Shard-level aggregate metadata is available. Per-sample selection statistics are not. |
| Uncovered clusters | Supported | Deferred | Cluster analysis depends on feature extraction and sample-level vectors. |
| Image upload | Supported | Unsupported | Individual image upload creates `SampleORM` rows. Sparse ingest is batch-oriented (parquet shard upload). |
| Sample import (parquet) | Supported | Supported | Parquet import is the primary ingest path for sparse datasets. For `db_full`, it materializes rows; for sparse, it registers shard manifests. |
| Agent chat | Supported | Supported | The global agent can query dataset-level metadata for both modes. Sample-level agent operations are unavailable for sparse datasets. |
| Dataset delete | Supported | Supported | Sparse delete cleans shard artifacts deterministically using dataset-owned prefixes. No per-image enumeration is needed. LS project deletion is skipped for sparse datasets. |

---

## Migration & Defaults

All existing datasets remain `db_full`. An Alembic migration sets `storage_mode = 'db_full'` as the default for existing rows and any future rows that don't explicitly opt in.

Sparse mode is strictly opt-in. No dataset is converted to sparse unless an operator explicitly creates it as `file_shard_sparse`. Seed scripts, test fixtures, and local dev flows continue to produce `db_full` datasets by default.

The `storage_mode` field is orthogonal to `dataset_type`. A classification dataset and a VQA dataset can each be either `db_full` or `file_shard_sparse`. Storage behavior is never inferred from the semantic type.

---

## Future Directions

The following sparse-native expansions are intentional non-goals for Phase 1. They are listed here to make the deferred scope explicit so future engineers don't mistake their absence for an oversight:

- **Sparse-native training**. Training flows currently enumerate `SampleORM` rows. A shard-backed training path requires significant rework of the training runner and orchestration layer.
- **Sparse-native export**. Export assumes full sample row materialization. Rebuilding it atop shard files is deferred.
- **Sparse-native feature extraction and similarity search**. These depend on per-sample vector storage that doesn't exist yet for sparse datasets.
- **Full sample browsing for sparse datasets**. Emulating `SampleORM` pagination over shard files is explicitly out of scope. The sparse interaction model is prediction review, not exhaustive browsing.

Phase 1 establishes the storage mode split, the capability matrix, and the adapter seams. Phase 2 and beyond will build sparse-native prediction, review, and eventually training and export on top of those foundations. The core principle remains: sparse mode does not aim for feature parity with `db_full`. It aims to support the large-dataset workflow on its own terms.
