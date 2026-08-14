# Dataset Summary, Collection Stack, and Dynamic Collection

Status: dataset-collection MVP implemented; summary and automation sections are proposals
Date: 2026-08-05

## 1. Scope

This document covers five related product capabilities:

1. a useful Dataset Summary view;
2. a Dataset Collection, also called a virtual dataset, that can train on data
   from multiple datasets;
3. an SC inspection-table action that imports selected inspections as
   standalone datasets and composes them into a collection;
4. a collection stack that can be opened in the classify workbench without
   losing the ability to open each member dataset on its own;
5. a Dynamic Dataset Collection whose immutable revisions are refreshed by a
   sensor or cron schedule.

The proposal does not make a collection another physical `DatasetORM`. A
dataset owns samples and storage; a collection owns a composition rule and
immutable revisions. Keeping these concepts separate avoids inventing a third
`storage_mode` and preserves the existing `DatasetStorageAgg` boundary.

This document does not amend `CORE_DESIGNS.md`.

### 1.1 Implemented MVP boundary

The current implementation includes:

- collection resources with audited, optimistic-lock link/unlink membership;
- synchronous immutable revision materialization with data and provenance
  Parquet artifacts;
- dataset-or-collection-revision inputs for training, prediction, and
  train-and-predict;
- prediction fanout to each physical source dataset;
- SC inspection multi-select import into standalone datasets followed by
  collection creation;
- collection list/detail pages, existing-dataset link/unlink, revision
  creation, and a stack classify route that switches among physical members;
- stable `row_key`/`sample_id` identity for SC table/gallery selection,
  annotation overlays, and prediction overlays.

The following sections also describe planned extensions that are not part of
this MVP: Dataset Summary, durable `dataset_import_sources`, combined
`All sources` classify queries, member filter/mapping/sampling transforms,
background refresh runs, sensors, and cron-driven dynamic revisions. The API
currently rejects non-empty member transform specifications explicitly.

The term **stack opening** in this proposal means opening several compatible
physical datasets through one collection workbench scope. It does not mean
merging the source datasets into a new `DatasetORM`, and it does not imply that
wafer geometries from different inspections can be overlaid on one map.

## 2. Product Model

### 2.1 Terms

| Term                 | Meaning                                                                                                                                           |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Dataset              | A physical platform dataset with one explicit `storage_mode`.                                                                                     |
| Collection           | A reusable logical definition containing one or more dataset sources and explicit composition rules.                                              |
| Collection revision  | An immutable, resolved snapshot of a collection definition and its source manifests. Training consumes this resource.                             |
| Collection workspace | The mutable collection head used for browse/classify. It resolves current member data and overlays but is never submitted to runtime as “latest”. |
| Static collection    | Membership changes only through an explicit user edit and revision creation.                                                                      |
| Dynamic collection   | The same collection model with one or more refresh bindings that request new revisions.                                                           |
| Refresh run          | One observable attempt to resolve a collection definition into a revision.                                                                        |
| Sample ref           | A typed physical identity: `(source_dataset_id, source_sample_id)`.                                                                               |
| Row key              | An opaque, deterministic UI/runtime row identity derived from a sample ref; unique within a collection scope.                                     |

“Dynamic” is behavior, not a second storage type. A collection can become
static or dynamic by adding or removing refresh bindings.

An SC inspection is an upstream source, not a collection member. It becomes
eligible for collection membership only after import creates a normal physical
dataset and a durable import-source record. This is what preserves standalone
dataset opening and storage ownership.

### 2.2 Core invariant

Training never consumes a mutable collection head.

```text
collection definition
        |\
        | \ current definition + source overlays
        |  v
        | collection classify workspace
        |
        | explicit refresh
        v
immutable collection revision
        |
        | materialize exact view contract
        v
job-scoped data-plane manifest
        |
        v
training or prediction job
```

The UI may offer “Refresh and train”, but it must perform and expose two
operations: create a successful revision, then submit training with that
revision ID. A job records the exact revision it used.

Prediction follows the same rule. A collection head is valid for interactive
browse/classify, but training, prediction, and train-and-predict accept only a
concrete ready revision. A source dataset remains valid as a direct job input.

## 3. Dataset Summary View

### 3.1 Navigation

Keep `/datasets/:id` as the dataset route. Make `Summary` the first/default tab
and store the selected tab in `?tab=` so refresh, deep links, and browser
navigation are stable.

Recommended tabs:

```text
Summary | Samples | Annotate | Train | Predict | Activity
```

Tabs are capability-driven. For example, a storage mode without Label Studio
support does not show an enabled Annotate tab; it shows the capability reason
in Summary. The page must check `storage_mode` explicitly rather than infer
behavior from `dataset_type`.

### 3.2 Summary layout

The first viewport answers “what is this data, is it usable, and what changed?”

1. **Identity and capabilities**
   - name, ID, dataset type, storage mode, owner, created time;
   - provided versioned view contracts;
   - supported actions with disabled reasons.
2. **Data health**
   - total samples, annotated samples, active classes;
   - train readiness and the existing explicit disabled reason;
   - schema/manifest status and last successful summary computation time.
3. **Label distribution**
   - labeled/unlabeled counts and per-label counts;
   - the SC 1,000-samples-per-class rule is shown when it applies.
4. **Storage**
   - `db_full`: sample and annotation facts;
   - `file_shard_sparse`: row count, shard count, bytes, schema, and manifest
     creation time;
   - no storage-specific endpoint is called unless the capability descriptor
     says it applies.
5. **Recent activity**
   - imports, annotation changes, predictions, training jobs, and refreshes
     from Task Tracker;
   - link to the complete Activity view.

Primary actions are `Browse samples`, `Add/Import`, and `Train`. Destructive or
less frequent actions stay in an overflow menu.

### 3.3 Summary API

Add one composition endpoint rather than making the page coordinate several
storage-specific calls:

```http
GET /api/v1/datasets/{dataset_id}/summary
```

Suggested response shape:

```json
{
  "dataset": {
    "id": "ds_123",
    "name": "Line A defects",
    "dataset_type": "sc",
    "storage_mode": "file_shard_sparse",
    "created_at": "2026-07-31T08:00:00Z",
    "created_by": "user_123"
  },
  "view_contracts": [{ "id": "sc.patch_image.v1", "schema_version": "1" }],
  "counts": {
    "total_samples": 120000,
    "annotated_samples": 8900,
    "active_class_count": 8
  },
  "label_counts": { "1": 1200, "2": 980 },
  "readiness": {
    "allow_train": true,
    "disabled_reason": null
  },
  "storage": {
    "manifest_status": "ready",
    "shard_count": 30,
    "size_bytes": 9300000000
  },
  "capabilities": [
    { "id": "train", "enabled": true, "reason": null },
    { "id": "label_studio", "enabled": false, "reason": "unsupported_storage_mode" }
  ],
  "computed_at": "2026-07-31T08:05:00Z"
}
```

`DatasetSummaryService` composes existing dataset metadata,
`DatasetStorageAgg.get_annotation_stats()`, training readiness, storage
metadata, and capability descriptors. The route remains thin.

Large summaries must not scan all rows during a page request. Introduce an
explicit summary refresh task and persist its result when a storage-backed
aggregate cannot answer from metadata. The API returns `pending`, `ready`, or
`failed` plus `computed_at`; it does not silently return stale or partial
numbers. The refresh trigger and freshness policy are implementation decisions,
not hidden defaults.

## 4. Dataset Collection

### 4.1 Data model

The control plane owns the following tables.

#### `dataset_collections`

| Field                                           | Notes                                                       |
| ----------------------------------------------- | ----------------------------------------------------------- |
| `id`, `org_id`, `name`, `description`           | Normal resource identity and ownership.                     |
| `target_view_contract`, `target_schema_version` | Exact runtime-facing contract selected for this collection. |
| `duplicate_policy`, `missing_data_policy`       | Required, explicit composition policies. No server default. |
| `definition_version`                            | Monotonic optimistic-lock version.                          |
| `created_by`, `created_at`, `updated_at`        | Audit fields.                                               |

#### `dataset_collection_members`

| Field                                                      | Notes                                                                        |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `id`, `collection_id`, `source_dataset_id`                 | A source belongs to the same organization.                                   |
| `position`                                                 | Stable order among active members; gaps are valid until an explicit reorder. |
| `linked_definition_version`, `unlinked_definition_version` | Definition-version interval in which this membership is active.              |
| `linked_by`, `linked_at`, `unlinked_by`, `unlinked_at`     | Lifecycle audit; null unlink fields mean the member is currently linked.     |
| `filter_spec`                                              | Versioned, validated filter AST; `{}` means an explicitly unfiltered source. |
| `label_mapping`                                            | Explicit source label to target label mapping.                               |
| `sampling_spec`                                            | Explicit include/weight/cap strategy; no implicit weighting.                 |

MVP should support whole-dataset membership first. Filter and sampling fields
are present in the contract only when their DSL and failure semantics are
specified; arbitrary SQL or Polars expressions are not accepted over HTTP.
The same physical dataset may occur only once among the active members of an
MVP collection. A partial unique index enforces
`(collection_id, source_dataset_id)` while `unlinked_at IS NULL`. Re-linking a
previously unlinked dataset creates a new member row and preserves the old row
for revision provenance. A later filter DSL can permit several non-overlapping
member slices only after duplicate semantics are specified. MVP has no second
`disabled` membership state: changing whether a source participates is an
audited link or unlink operation.

#### `dataset_import_sources`

This generic control-plane table makes imported upstream identity queryable
without scanning `DatasetORM.dataset_meta` JSON.

| Field                        | Notes                                                                                        |
| ---------------------------- | -------------------------------------------------------------------------------------------- |
| `id`, `org_id`, `dataset_id` | The imported physical dataset and tenant.                                                    |
| `provider`, `source_kind`    | For this flow: `sc` and `inspection`.                                                        |
| `source_key`                 | Canonical provider-owned key for inspection time plus wafer key.                             |
| `source_snapshot`            | Display/audit metadata such as inspection time, wafer key, lot, wafer, layer, and equipment. |
| `imported_at`, `created_by`  | Audit fields.                                                                                |

The lookup index is `(org_id, provider, source_kind, source_key)`. Multiple
datasets may point to the same upstream source because such imports can already
exist. If the lookup returns more than one candidate, the UI requires an
explicit dataset choice; it must not silently select the newest dataset.

#### `dataset_collection_revisions`

| Field                                                     | Notes                                                                                                 |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `id`, `collection_id`, `revision_number`                  | Immutable collection snapshot identity.                                                               |
| `definition_version`, `definition_hash`                   | Exact definition that was resolved.                                                                   |
| `target_view_contract`, `target_schema_version`           | Frozen compatibility boundary.                                                                        |
| `status`                                                  | `pending`, `ready`, or `failed`.                                                                      |
| `source_snapshot`                                         | Source dataset IDs, storage modes, manifest/version refs, filters, mappings, and source fingerprints. |
| `row_count`, `label_counts`                               | Revision summary when ready; label counts describe the frozen label snapshot used by runtime.         |
| `manifest_uri`, `provenance_uri`                          | Resolved collection manifest and row provenance sidecar.                                              |
| `trigger_kind`, `trigger_ref`, `created_by`, `created_at` | Audit and automation provenance.                                                                      |
| `error_code`, `error_detail`                              | Explicit failure result.                                                                              |

#### `dataset_collection_refresh_runs`

Tracks idempotency key, requested definition version, triggering event or
schedule run, state, timestamps, resulting revision, and error. Task Tracker
links to this record.

### 4.2 Link and unlink lifecycle

A collection has a mutable **head definition** and zero or more immutable
revisions. Linking and unlinking existing datasets edits only the head:

- **Link** validates one or more existing physical datasets against the
  collection's organization and exact target view contract, creates active
  member rows at explicitly requested positions, and increments
  `definition_version` once for the atomic request.
- **Unlink** closes one active membership's definition-version interval and
  increments `definition_version`. It does not delete the membership audit row
  or renumber the remaining positions implicitly.
- Both operations require `expected_definition_version`. A stale request fails
  with `409 definition_version_conflict`; no subset of the request is applied.
- Linking an already active dataset fails with `409 dataset_already_linked`.
  Unlinking a missing or already inactive member fails explicitly rather than
  pretending that a state change occurred.

Link and unlink never delete, move, rewrite, or change ownership of the source
dataset, its samples, annotations, predictions, import-source record, or
standalone route. Unlinking is therefore reversible by linking that physical
dataset again. Source deletion is a separate operation: it is rejected while
an active collection member or any retained collection revision references the
dataset, unless an accepted revision-retention policy has first made every
historical reference self-contained.

An existing ready revision is not modified when the head changes. Training or
prediction jobs pinned to that revision continue against its immutable
manifest. A revision or refresh run that observes a membership change while
resolving fails with `definition_changed`; it never publishes a mixed snapshot.
Linking or unlinking does not silently create a revision. The UI exposes the
head as changed and requires an explicit `Refresh revision` before a new job
can use the new composition.

Each successful membership mutation publishes a collection-scope
`definition_changed` event containing the new `definition_version` and the
linked/unlinked member IDs. An open classify workbench invalidates its mutable
head query and reloads the source stack. Existing rows keep the same `row_key`.
If an unlinked source owns the active map, the UI clears that active-source
choice and asks the user to choose another; it does not silently switch source
context.

Selection or annotation drafts for an unlinked source must not be silently
discarded or submitted against the new head. They move to a recoverable
detached-draft state keyed by `row_key`; the user can open the standalone
dataset to apply them, re-link the dataset, or explicitly discard them. Any
stale annotation request carrying the previous definition version fails with
`409 definition_version_conflict`.

The recommended MVP permits unlinking the last member, leaving an empty draft
head so the collection resource and audit history remain available. Classify,
revision creation, training, and prediction then fail with/return a visible
`no_active_members` readiness reason until another dataset is linked. This
empty-head behavior remains an explicit product decision in Section 11.

### 4.3 Identity contract

`defect_id` is an SC domain identifier. It is not unique across inspections and
must not key collection rows, selections, annotation drafts, overlay joins, or
prediction writeback. A collection uses this typed identity:

```json
{
  "source_dataset_id": "ds_123",
  "source_sample_id": "48152"
}
```

The API also exposes an opaque deterministic `row_key` derived from that pair.
The exact encoding is server-owned and clients do not parse it. It remains
stable when the same source sample appears in later revisions, which preserves
selection and draft continuity. The physical pair remains in the provenance
record and is the authority for writes.

SC workbench rows expose both identities:

```json
{
  "row_key": "sr_01...",
  "source_dataset_id": "ds_123",
  "source_sample_id": "48152",
  "inspection_time": "2026-08-05T10:00:00+08:00",
  "wafer_key": 991,
  "defect_id": "48152"
}
```

For a standalone dataset workbench, the server synthesizes the same `row_key`
from that dataset and sample. For an unimported inspection preview, it may
synthesize an inspection-scoped preview key, but preview keys are not accepted
by collection, annotation, training, or prediction APIs.

The workbench transport and the runtime view are different contracts. The
workbench may expose provenance/display columns. A runtime collection manifest
keeps the trainer's exact canonical view schema and uses `row_key` as the
manifest-local `sample_id`; the sidecar maps it back to the physical sample
ref. This does not add undeclared columns to a trainer view.

### 4.4 Compatibility rules

A member does not need the same `dataset_type` or `storage_mode` as another
member. It must have a registered materializer that can produce the
collection's exact target `ViewContractRef`.

Revision creation fails before training when:

- a source is missing or belongs to another organization;
- no registered materializer can produce the target view and schema version;
- required columns or images are unavailable;
- label spaces conflict without an explicit mapping;
- the selected deduplication, sampling, or missing-data policy is absent;
- a source changed while its revision was being resolved and the source cannot
  provide a stable snapshot.

These failures are visible on the revision and in Task Tracker. There is no
fallback to another view contract, schema version, or storage path.

### 4.5 Composition and provenance

Collection materialization is bulk/table-first:

1. open every source through `DatasetStorageFactory`;
2. resolve its registered view materializer;
3. obtain stable source manifest refs;
4. compose with LazyFrame/Arrow scans, projections, joins, and streaming
   writers;
5. write canonical job/revision shards for the exact target view;
6. write a provenance sidecar keyed by output row identity;
7. persist the immutable collection revision manifest.

The provenance sidecar includes at least:

```text
output_row_id
source_dataset_id
source_sample_id
source_manifest_fingerprint
member_id
```

This keeps platform provenance available without adding undeclared columns to
the trainer's canonical view schema.

A ready revision pins its source refs. Dataset deletion must either be rejected
while a retained revision references it or follow an explicitly accepted
revision-retention policy. It must not silently make a historical training job
irreproducible.

### 4.6 Classify/read contract

The combined collection classify page reads one explicit immutable revision
through an SC data-provider collection scope:

```text
POST /api/v1/sc/data/collections/{collection_id}/revisions/{revision_id}/query
GET  /api/v1/sc/data/collections/{collection_id}/revisions/{revision_id}/events
```

`ScDataScope(kind="collection")` downloads the pinned revision artifact,
opens every source overlay through `DatasetStorageFactory`, projects a
compatible workbench schema, adds the identity columns above, and composes the
sources with LazyFrame/Arrow union. It does not instantiate storage
implementations or read shards ad hoc. Link/unlink changes therefore become
visible after a new ready revision is created; an already-open historical
revision does not drift.

The DuckDB `samples` view, pagination CTEs, annotation overlay, prediction
overlay, gallery, and annotation drafts use `row_key`. `defect_id` remains a
filterable/display column and may match multiple rows. The existing numeric map
component receives revision-local `map_id` values as its dictionary key; SQL
selection filters use that key while physical writes resolve through
`row_key`. A source `defect_id` is never used as a collection selection
identity.

Collection annotation requests carry `row_key` plus the expected collection
definition version. The collection service resolves physical sample refs,
groups writes by `source_dataset_id`, opens each `DatasetStorageAgg`, and writes
annotations through the aggregate. Successful writes are therefore visible
when a member dataset is opened standalone. A partial multi-source annotation
write is reported per source and is never returned as an all-success response.

Collection-scope invalidation listens to changes for every member dataset and
increments one collection scope revision. The data provider continues to cache
immutable base/overlay objects, not final SQL results.

### 4.7 Training and prediction contract

The runtime now replaces the assumption that every training input is a mutable
`dataset_id` with an exact source reference. The transport keeps backward
compatible top-level fields:

```json
{
  "collection_id": "col_123",
  "collection_revision_id": "colrev_7",
  "trainer_id": "sc.resnet50.train.v1",
  "parameters": {}
}
```

A normal dataset uses:

```json
{
  "dataset_id": "ds_123"
}
```

Training and prediction jobs persist the full typed reference. Dataset-only
callers may use the existing request shape during a documented migration
period, but collection IDs must never be placed in `dataset_id`.

Prediction uses the same union:

```json
{
  "collection_id": "col_123",
  "collection_revision_id": "colrev_7",
  "model_id": "model_123",
  "predictor_id": "sc.resnet50.predict.v1"
}
```

The request/domain boundary normalizes those fields into
`RuntimeDataSourceRef`. Dataset inputs open one `DatasetStorageAgg`; collection
revision inputs resolve a ready, immutable artifact. Generic runtime hosts
remain source-agnostic; the registered SC runtime module owns source loading
and collection prediction fanout.

For train-and-predict, the same revision drives both phases. The visible SC
1,000-samples-per-class training cap is applied after collection membership and
workflow filters, ordered by stable `row_key`. Prediction retains the full
original revision scope, including rows held out of training.

Prediction output is keyed by manifest `sample_id` (`row_key`). A collection
writeback adapter joins the provenance sidecar in bulk, partitions results by
physical source dataset, and calls each source `DatasetStorageAgg.write_predictions`.
Predictions consequently remain visible from standalone member datasets. The
job retains its collection revision provenance even though result rows are
owned by physical source storage.

The revision stores a provenance sidecar next to its materialized data. A
future data-plane manifest schema can expose the collection-revision source and
sidecar directly without changing trainer input contracts.

## 5. Collection UI

Use a separate route and resource page:

```text
/dataset-collections
/dataset-collections/:id
```

List datasets and collections together on the top-level Data surface only if
each row has a clear `Dataset` or `Collection` badge. Do not make a collection
look like a physical dataset.

Recommended detail tabs:

```text
Summary | Sources | Classify | Revisions | Train | Predict | Automations | Activity
```

### SC inspection-table entry flow

`/sc/preview` adds checkbox selection to the inspection summary table. Its row
key remains the upstream inspection tuple for table selection only:

```text
(inspection_time, wafer_key)
```

The selection toolbar exposes `Build collection (N)`. The wizard performs
these explicit steps:

1. Resolve `dataset_import_sources` for every selected inspection.
2. For an unimported inspection, import a normal `file_shard_sparse` SC
   dataset and persist its import-source record.
3. If several imported datasets represent one inspection, require the user to
   choose one.
4. Show compatibility, label-space, missing-data, and duplicate-policy
   validation for the full selection.
5. Create the collection and atomically replace its ordered members.
6. Create the first revision. Enable `Open collection` only when that revision
   is ready; keep every imported dataset independently openable even if another
   import or revision fails.

Import progress is durable and reported per inspection through Task Tracker.
Batch concurrency must be an explicit configured product/runtime limit with a
visible failure state; it is not inferred from selection size. A failed member
does not cause already imported physical datasets to be deleted. The collection
is not published as ready until all selected members have resolved.

The dataset list also offers `Open as collection` for any explicitly selected
set of already imported datasets that can produce the same target view. This
is the general composition path; the SC inspection table is a convenient
import-aware entry point, not a separate collection type.

### Collection classify stack

The route is:

```text
/dataset-collections/:collectionId/classify/:datasetId?revisionId=:revisionId
```

The page reuses the SC dataset workbench and opens the revision as one combined
table/gallery/filter/sampling scope. Each member remains independently
openable through the existing dataset route. Training and prediction use the
same `revisionId` carried by the collection route.

- The combined mode covers table, gallery, filters, distribution, sampling,
  drafts, and bulk annotation across compatible members.
- Patch/review image requests use each row's source inspection, wafer, dataset,
  and sample identity instead of the route's representative dataset.
- Selection and annotation drafts use `row_key`. The UI may display
  `defect_id`, inspection, wafer, lot, and member name, but none of those
  display fields is used as a collection row key.
- `Open dataset` on every source opens the existing standalone route. A
  collection never replaces or redirects that route.
- Train and Predict require an explicit ready revision. If the collection
  definition or source fingerprints changed, the page requires a revision
  refresh; it does not submit a mutable “latest” head.

For MVP, “any composition” means any ordered set of already imported physical
datasets compatible with one exact target view contract. Arbitrary row slices,
weights, joins, and overlapping filters remain Phase 6 until their DSL and
failure semantics are accepted.

### Summary

- target view contract and schema version;
- current definition version;
- latest ready revision with sample and label counts;
- compatibility/readiness state;
- source count, dynamic/static state, and next cron run if present;
- last refresh, last successful revision, and latest error.

### Sources

The editor validates all members as a set. It displays source compatibility,
storage mode, label mapping, filters, sampling rule, and estimated counts.
`Link datasets` opens an organization-scoped, multi-select picker for existing
physical datasets and shows incompatible candidates with the exact validation
reason. It never imports or clones a dataset as a side effect. Each active
source exposes `Open dataset` and `Unlink` actions.

An unlink confirmation names the affected source and explains that the
standalone dataset and historical revisions remain available. If the source
owns local selections or annotation drafts, unlink also requires an explicit
choice to preserve them as detached drafts or cancel the operation. A remote
unlink received while the page is open always preserves such local state.

The page shows when the mutable head differs from the latest ready revision.
Linking, unlinking, reordering, or editing composition settings increments
`definition_version`; none of those operations mutates an existing revision.
An empty head remains on the Sources tab with a visible `no_active_members`
readiness reason and a `Link datasets` action.

### Revisions

Show immutable revision number, trigger, definition version, source
fingerprints, counts, status, creator, time, and jobs using the revision. A
revision can be inspected or used for training, but never edited.

### Train

The user selects a ready revision. “Latest” may be a UI label, but the submitted
request always contains a concrete revision ID. If the definition has changed
since that revision, the UI exposes `Refresh revision` before training.

### Automations

Show sensor and cron bindings, enabled state, last/next run, recent refresh
result, and a test/refresh-now action. Editing automation never rewrites an
existing revision.

## 6. Automated Collection Refresh

Interactive link/unlink edits are the head-definition lifecycle in Section
4.2. This section defines automated revision refresh. A refresh binding does
not implicitly add or remove members; event-derived membership changes require
a separately registered source adapter and typed action contract.

### 6.1 One refresh action, two trigger sources

Both sensors and cron invoke the same registered control-plane action:

```text
refresh_dataset_collection.v1
```

Its typed parameters are:

```json
{
  "collection_id": "col_123",
  "expected_definition_version": 4
}
```

An event may supply values accepted by a registered collection source adapter,
but arbitrary event payload is not merged into action parameters.

```text
sensor event ─┐
              ├─> trigger binding ─> refresh action ─> refresh run ─> revision
cron schedule ┘
```

### 6.2 Binding model

Add `dataset_collection_refresh_bindings`:

| Field                               | Notes                              |
| ----------------------------------- | ---------------------------------- |
| `id`, `org_id`, `collection_id`     | Organization-scoped ownership.     |
| `trigger_kind`                      | `sensor` or `cron`.                |
| `sensor_subscription_id`            | Required only for sensor bindings. |
| `schedule_id`                       | Required only for cron bindings.   |
| `enabled`, `created_by`, timestamps | Lifecycle and audit.               |

Exactly one trigger reference is set. The binding points at the existing
sensor/schedule subsystem rather than creating a second scheduler.

Cron uses the existing Schedule service with
`flow_name=refresh_dataset_collection.v1` and typed collection parameters.
The collection page creates and manages the schedule through a
collection-owned application service, not by duplicating Prefect calls in the
route.

### 6.3 Sensor prerequisites

The existing sensor implementation cannot safely own dynamic collection
refreshes yet:

- `sensor_subscriptions` has no `org_id`;
- sensor routes do not currently require user and organization context;
- `workflow_type` is a raw string resolved directly to a Prefect deployment;
- the stored subscription has filters but no typed action parameters;
- matching is flat equality and does not validate `filter_config` against the
  sensor's JSON Schema.

Before collection binding:

1. add `org_id`, `created_by`, and their Alembic migration;
2. enforce auth and organization filtering in routes and repositories;
3. replace or version `workflow_type` with a registered action descriptor ref;
4. persist and validate typed `action_config`;
5. validate filter configuration using the registered sensor definition;
6. include organization and an immutable event ID in dispatch;
7. route actions through an application port rather than resolving arbitrary
   deployment strings in `SensorDispatchService`.

The existing YAML sensor definitions are legacy registry inputs. This feature
does not add collection-specific YAML or another preset mechanism. New
collection refresh actions and source adapters use module-owned descriptors
registered through the application registration barrel.

### 6.4 Idempotency and concurrency

Each trigger creates a refresh request with an idempotency key:

```text
sensor: hash(sensor_id, event_id, binding_id, definition_version)
cron:   hash(schedule_id, scheduled_time, binding_id, definition_version)
manual: caller-supplied idempotency key
```

Only one active refresh run is allowed for the same collection definition
version. A duplicate trigger returns the existing run. If a run resolves to the
same source fingerprint and definition hash as the latest ready revision, it
completes as `unchanged` and points to that revision rather than creating an
indistinguishable revision.

If the definition changes during resolution, the run fails with
`definition_changed`; it does not publish a revision based on mixed versions.

## 7. API Surface

Implemented MVP endpoints:

```text
POST   /api/v1/dataset-collections
GET    /api/v1/dataset-collections
GET    /api/v1/dataset-collections/{id}
PATCH  /api/v1/dataset-collections/{id}
DELETE /api/v1/dataset-collections/{id}

GET    /api/v1/dataset-collections/{id}/members
POST   /api/v1/dataset-collections/{id}/members
PUT    /api/v1/dataset-collections/{id}/members
DELETE /api/v1/dataset-collections/{id}/members/{member_id}

POST   /api/v1/dataset-collections/{id}/revisions
GET    /api/v1/dataset-collections/{id}/revisions
GET    /api/v1/dataset-collections/{id}/revisions/{revision_id}

POST   /api/v1/training-jobs
POST   /api/v1/training-jobs/train-and-predict
POST   /api/v1/predictions/run
```

Dataset summary, import batches/source resolution, combined collection
annotations/query/events, and refresh-binding endpoints described elsewhere in
this document are planned extensions.

`POST /members` links one or more existing datasets atomically. Its body carries
`expected_definition_version` and an explicit ordered list of
`source_dataset_id`, `position`, and any accepted composition fields. Every
candidate is organization-, capability-, and whole-definition validated before
any row is created.

`DELETE /members/{member_id}` unlinks one active member and requires
`expected_definition_version` as an explicit request parameter. It closes the
membership lifecycle interval; it does not delete the row or source dataset.
The response from each successful membership mutation includes the new
`definition_version`, active ordered members, and latest-ready-revision status.

`PUT /members` remains the atomic full-replacement/reorder operation used by
the creation wizard and bulk editor. It performs the equivalent audited link,
unlink, and reorder transitions in one transaction rather than deleting all
member rows. All membership mutations return `409` on a definition-version
conflict, and partial changes never leave a half-valid collection.

Collection metadata, membership, and revision mutations are creator-only and
return `403` for another organization member instead of surfacing an internal
error. Deleting a collection first removes its database state, then
best-effort deletes every retained revision data/provenance artifact. A
collection pinned by an existing training or prediction job is not deleted and
returns `409 collection_in_use`, preserving the job's immutable input.

The future collection SSE stream can publish membership changes as:

```text
event: definition_changed
data: {collection_id, definition_version, linked_member_ids, unlinked_member_ids}
```

Clients use the event only to invalidate and refetch authorized state; it is
not a substitute for the collection response DTO or a runtime manifest.

`POST /api/v1/dataset-import-sources/resolve` accepts a bounded explicit list
of typed source refs and returns every matching dataset candidate per ref. The
request must provide the list; the server does not apply an implicit result
limit. `POST /api/v1/sc/import-batches` accepts the selected, unresolved
inspections and an explicit concurrency requested within the configured
allowed range. Batch and member state are persisted, and its status and SSE
stream report each member independently. Execution uses the existing direct SC
import service behind a typed port and does not reintroduce an `sc_import`
Prefect deployment.

All new request/response DTOs originate in route/schema code and are exported
through `make generate`. `openapi/openapi.yaml` is not edited manually.

Training and prediction transport DTOs expose mutually exclusive
`dataset_id` or `collection_id` plus `collection_revision_id` fields. Domain
commands normalize those fields into a discriminated `RuntimeDataSourceRef`.
Requests that mix source shapes are rejected.

`training_jobs` and `prediction_jobs` now persist nullable dataset,
collection, and collection-revision columns. Request/domain validation enforces
the exact source shape; historical direct-dataset jobs may have a null
`dataset_id` after source deletion. A future migration can add a database check
that also accounts for that historical tombstone shape.

One future collection data-plane manifest shape could replace the v1 top-level
dataset assumption with:

```json
{
  "source": {
    "kind": "collection_revision",
    "collection_id": "col_123",
    "revision_id": "colrev_7"
  },
  "provenance": {
    "uri": "s3://.../provenance.parquet",
    "key_column": "output_row_id"
  }
}
```

The existing `view_contract`, `view_schema_version`, table schema, shards,
image policy, counters, auth, and lifecycle rules continue to apply.

## 8. Module Boundaries

Recommended backend module:

```text
apps/api/app/modules/dataset_collections/
  domain/
  app/services/
  adapter/repositories/
  adapter/materializers/
  port/http/
  port/local/
```

The module depends on typed dataset, materializer/catalog, scheduling, sensor
action, and Task Tracker ports. It does not import sibling repositories or ORM
models directly.

The dataset module continues to own physical sample/storage behavior. The
dataset/import boundary owns durable import-source lookup. The SC import
service writes `provider=sc`, `source_kind=inspection` through that typed port;
the collection module does not inspect `dataset_meta` JSON.

The dataset deletion guard depends on a typed collection-usage port. The
collection module reports active memberships and retained revision references
under the accepted retention policy; the dataset module does not query
collection tables or repositories directly.

The training and prediction modules accept a typed data-source resolver port
and remain unaware of collection persistence details. The collection module
implements collection-revision resolution and provenance-aware prediction
writeback behind ports. Runtime services receive only the versioned data-plane
manifest.

The separate SC data-provider composition root installs only the storage,
collection-read, revision, Redis, and query dependencies needed for collection
scopes. It must not import the full HTTP API composition or collection concrete
repositories from route code.

Frontend code lives under:

```text
apps/web/src/features/dataset-collections/
```

The collection creation flows compensate for their two-request
create-then-link transport: when membership linking fails, they delete the
newly created empty collection. Existing-dataset creation also validates the
MVP's identical ordered label-space rule before submission. Historical ready
revisions remain openable in classify even when the mutable collection head is
currently empty.

Collection source editors, automation editors, and summary panels are
registered through descriptors where they are extension points. The app
registration barrel performs registration; pages do not add dataset-type
switch statements.

The SC workbench contracts are updated once and shared by standalone and
collection routes:

- replace `selectedDefectIds`/`annotationDraft[defectId]` interaction identity
  with `selectedRowKeys`/`annotationDraft[rowKey]`;
- change table/gallery/map selection payloads to `row_key` while retaining
  `defect_id` as a column;
- extend `ScSqlWorkbenchScope`, `useScDataWorkbench`, and data-provider URL
  construction with collection scope;
- make geometry/source context a selected stack member rather than one
  dataset-level `source_inspection_time` assumption.

## 9. Delivery Plan

### Phase 1: Dataset Summary

- add the composed summary DTO/service/endpoint;
- add Summary and Samples tabs to the dataset page;
- add capability/readiness and storage-aware cards;
- add focused API, component, and route tests.

### Phase 2: Static Collection Foundation

- add ORM models and Alembic migration;
- persist/query durable dataset import-source identities;
- implement collection CRUD, audited link/unlink, atomic member editing,
  optimistic concurrency, and compatibility checks;
- implement immutable revision resolution and collection manifest v2;
- add collection list/detail/source/revision UI, including the existing-dataset
  picker and empty-head readiness state.

### Phase 3: Inspection Selection and Collection Classify

- add multi-selection plus the import/collection wizard to the SC inspection
  table;
- migrate SC workbench identity from `defect_id` to `row_key` for standalone
  and collection scopes;
- add collection scope to the SC data provider, including member invalidation;
- add the collection source stack and single-active-source map behavior;
- preserve detached selections/drafts when an open source is remotely unlinked;
- add provenance-aware multi-source annotation writes.

### Phase 4: Collection Train and Predict

- change training, prediction, and train-and-predict submission to accept a
  typed data source;
- persist typed data sources on jobs and model artifacts;
- resolve collection revisions through the data-plane manifest boundary;
- add provenance-aware prediction writeback to physical member datasets;
- add collection Train/Predict UI and task views.

### Phase 5: Automated Collection Refresh

- harden sensor tenancy, auth, validation, and typed actions;
- register `refresh_dataset_collection.v1`;
- add sensor and cron bindings plus idempotent refresh runs;
- expose automation state in Collection and Task Tracker UI.

### Phase 6: Advanced Composition

- introduce a versioned filter AST;
- add explicit label mapping, deduplication, sampling, and weighting policies;
- add source adapters for event-derived dynamic membership if required.

Do not include Phase 6 behavior implicitly in the static collection phases.

### Management UI behavior

- Dataset Detail opens on the persisted dataset contract. Training and
  prediction are embedded sections of that page, so they must not render a
  second page header or refetch the selected dataset merely to label the form.
- Collection Detail presents the mutable definition and latest ready revision
  as separate states. When they differ, creating the current revision is the
  primary action and reviewing the older revision must identify its revision
  number explicitly.
- Management tables keep stable column widths and horizontal scrolling on
  compact screens. Below the application breakpoint, the global navigation
  collapses to its icon rail so page content retains usable width.

## 10. Required Verification

- backend: repository/service/route tests, organization-isolation tests,
  revision concurrency tests, import-source ambiguity tests, manifest contract
  tests, and `make generate` plus `make test`;
- frontend: component tests, mock E2E for static and dynamic collection flows,
  `make test-web`, and `make build-web`;
- route/user-flow changes: `make test-e2e`;
- all code changes: `make lint` first, followed by the narrowest relevant
  checks;
- identity: a collection test where two inspections contain the same
  `defect_id`, proving selection, drafts, annotation overlays, and prediction
  writeback remain separate;
- standalone preservation: annotations and predictions made through a
  collection are visible when each member dataset is opened directly;
- membership lifecycle: link multiple existing datasets atomically, reject
  duplicate and cross-organization links, detect concurrent link/unlink
  conflicts, and prove unlink/re-link retains audit history;
- unlink isolation: unlink a source while its standalone route and an old
  revision-backed job remain usable, and prove the source dataset is neither
  deleted nor mutated;
- open-workbench mutation: receive link/unlink invalidation while classify is
  open, keep surviving `row_key` values stable, clear an unlinked active map,
  preserve detached drafts, and reject stale annotation submission;
- empty head: unlink the final source, expose `no_active_members`, and reject
  revision, training, and prediction creation until a source is linked;
- collection training/prediction: a smoke test proving two datasets with
  different storage modes can materialize the same exact view contract, train
  from the recorded revision, predict the full revision scope, and write back
  through provenance;
- failure semantics: tests for one failed source import, one failed source
  annotation write, changed definition during revision creation, and deletion
  of a referenced source.

## 11. MVP Decisions and Open Extensions

The implemented MVP makes these explicit choices:

1. source deletion is rejected while an active membership or retained revision
   references the dataset;
2. composition is whole-dataset concatenation with `keep_all` and `fail` as
   required request values; non-empty filter, mapping, and sampling specs are
   rejected;
3. member datasets must expose the exact same ordered label space;
4. collection prediction results are written through to the physical member
   datasets using revision provenance;
5. revision creation is explicit and synchronous; linking or unlinking does not
   publish a revision automatically.

Refresh publication/idempotency, summary freshness, transform DSL semantics,
and combined collection annotation ownership remain decisions for the planned
extensions described above. 8. **Collection prediction ownership:** partition and write back to physical
member storage, as proposed, or retain collection-only prediction shards. 9. **SC map behavior:** one active member map, as proposed, or define a valid
multi-inspection map visualization. 10. **Import publication:** publish the collection only after all selected
inspections import successfully, as proposed, or permit a visibly partial
collection definition. 11. **Empty collection head:** permit unlinking the last member and retain an
empty draft resource with disabled classify/job readiness, as proposed, or
reject the final unlink. 12. **Detached workbench drafts:** preserve drafts from a remotely unlinked
source for standalone/re-link recovery, as proposed, or define another
explicit conflict workflow.

Recommended MVP baseline for acceptance is: block deletion while a retained
revision references a source; whole-dataset ordered concatenation; require an
explicit `keep_all` duplicate policy; require identical label spaces; publish a
new revision only when source or definition fingerprints change; write
annotations and predictions through to source datasets; show one active wafer
map; publish the collection only after all selected imports succeed; treat
link/unlink as audited mutable-head edits; allow an empty draft head; and
preserve detached drafts after remote unlink. These are recommendations, not
accepted core decisions, until the product owner confirms them.
