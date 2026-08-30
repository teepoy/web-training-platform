# Dataset Summary, Collection Stack, and Rule-Managed Collection

Status: accepted Revision-only semantics, with planned Dataset Summary extensions
Date: 2026-08-15

The Collection feature uses **Revision** terminology only. A Revision is an
immutable publication of member identity, ordering, and rules; it is not a
frozen copy of member Dataset contents. Classify, training, and prediction
always resolve current Dataset rows, annotations, predictions, and mutable
upstream fields. A Revision does not create a retained member union, copy
member rows or images, or provide data time travel.

This replaces the Collection publication semantics previously described by
ADR 0014. ADR 0014 remains relevant to lightweight Dataset audit revisions,
but its Collection `Update available` and explicit republishing flow are
superseded by `CORE_DESIGNS.md`. The implemented automation surface is an active Collection
membership rule evaluated every five minutes. There is no generic Sensor API,
YAML registry, persistence model, or UI.

## 1. Scope

This document covers five related product capabilities:

1. a useful Dataset Summary view;
2. a Dataset Collection, also called a virtual dataset, that can train on data
   from multiple datasets;
3. an SC inspection-table action that imports selected inspections as
   standalone datasets and composes them into a collection;
4. a collection stack that can be opened in the classify workbench without
   losing the ability to open each member dataset on its own;
5. a rule-managed Dataset Collection whose source-discovery runs can admit
   members and publish a new Revision.

The proposal does not make a collection another physical `DatasetORM`. A
dataset owns samples and storage; a collection owns a composition rule and
immutable definition revisions. Keeping these concepts separate avoids inventing a third
`storage_mode` and preserves the existing `DatasetStorageAgg` boundary.

This document does not amend `CORE_DESIGNS.md`.

### 1.1 Implemented MVP boundary

The current implementation includes:

- collection resources with audited, optimistic-lock link/unlink membership;
- immutable Collection Revisions that record member identity, ordering, and
  rules without copying member rows or pinning Dataset contents;
- dataset-or-collection-revision inputs for training, prediction, and
  train-and-predict;
- prediction fanout to each physical source dataset;
- SC inspection multi-select import into standalone datasets followed by
  collection creation;
- collection list/detail pages, existing-dataset link/unlink, Revision
  publication, and a classify route with a selected-member union plus one
  active inspection for the map;
- stable `row_key`/`sample_id` identity for SC table/gallery selection,
  annotation overlays, and prediction overlays.

The following sections also describe planned extensions that are not part of
this MVP: Dataset Summary, durable `dataset_import_sources`, and advanced
member filter/mapping/sampling transforms. The API currently rejects non-empty
member transform specifications explicitly.

The term **stack opening** in this proposal means opening several compatible
physical datasets through one collection workbench scope. It does not mean
merging the source datasets into a new `DatasetORM`, and it does not imply that
wafer geometries from different inspections can be overlaid on one map.

## 2. Product Model

### 2.1 Terms

| Term                    | Meaning                                                                                                               |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Dataset                 | A physical platform dataset with one explicit `storage_mode`.                                                         |
| Collection              | A reusable logical definition containing one or more dataset sources and explicit composition rules.                  |
| Collection Revision     | An immutable publication of member identities, ordering, rules, and mappings. It does not freeze member Dataset data. |
| Collection workspace    | The classify surface for one explicit Revision. It resolves current data for the selected Revision members.           |
| Static collection       | Membership changes only through explicit user edits; a successful member batch publishes the resulting Revision.      |
| Rule-managed collection | The same Collection model whose typed membership rule admits sources through discovery runs.                          |
| Publication run         | One manual batch, Discovery run, or Backfill that may publish at most one new Revision.                               |
| Sample ref              | A typed physical identity: `(source_dataset_id, source_sample_id)`.                                                   |
| Row key                 | An opaque, deterministic UI/runtime row identity derived from a sample ref; unique within a collection scope.         |

Rule-managed admission is behavior, not a second storage type. A Collection
can combine manually linked members and members admitted by its typed rule.

An SC inspection is an upstream source, not a collection member. It becomes
eligible for collection membership only after import creates a normal physical
dataset and a durable import-source record. This is what preserves standalone
dataset opening and storage ownership.

### 2.2 Core invariant

Training never consumes an ambiguous mutable Collection head.

```text
collection definition
        |
        | successful manual batch, Discovery, or Backfill
        v
immutable Collection Revision
        |
        | resolve selected members' current data
        v
classify workspace or job-scoped runtime view
        |
        v
training or prediction job
```

Prediction follows the same rule. Classify, training, prediction, and
train-and-predict accept a concrete ready Revision and record its ID as
definition provenance. Member Dataset or upstream value changes are read
dynamically and do not require a new Revision. A source Dataset remains valid
as a direct job input.

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
   - imports, annotation changes, predictions, training jobs, and summary tasks
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

| Field                                                             | Notes                                                                                              |
| ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `id`, `collection_id`, `revision_number`                          | Immutable Collection Revision identity.                                                            |
| `definition_version`, `definition_hash`                           | Exact member and rule definition that was published.                                               |
| `target_view_id`, `target_view_contract`, `target_schema_version` | Frozen compatibility boundary.                                                                     |
| `status`                                                          | `pending`, `ready`, or `failed`.                                                                   |
| `members`                                                         | Ordered member IDs, Dataset IDs, positions, and versioned filter/mapping/sampling rule identities. |
| `manifest_uri`                                                    | Optional implementation reference for the lightweight definition manifest; never a copied union.   |
| `trigger_kind`, `trigger_ref`, `created_by`, `created_at`         | Manual batch, Discovery, or Backfill publication provenance.                                       |
| `error_code`, `error_detail`                                      | Explicit publication failure.                                                                      |

The Revision deliberately has no Dataset Revision pins, member row counts,
label-count cache, source-resolution mode, reproducibility flag, or retained
provenance sidecar. Current counts come from the selected members at read time.

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
dataset again. Source deletion is a separate operation and must respect active
and historical member-reference retention rules.

An existing ready Revision is not modified when the head changes. Training or
prediction jobs that record that Revision continue to use its published member
and rule definition while resolving those members' current data. A publication
run that observes a definition change while resolving fails with
`definition_changed`; it never publishes a mixed definition. A successful
manual member batch, Discovery run, or Backfill may publish at most one
Revision. Users do not republish a Revision because a member Dataset publishes
a new Dataset Revision or an upstream field changes.

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
Revision publication, training, and prediction then fail with/return a visible
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
Revision does not contain a second copy of runtime rows. When a runtime needs a
unified table, it resolves each selected member's current data at execution
start and derives a job-scoped disposable view. That cache namespaces row
identity by member Dataset, can be rebuilt, and is not an archived fact source.

### 4.4 Compatibility rules

A member does not need the same `dataset_type` or `storage_mode` as another
member. It must have a registered materializer that can produce the
collection's exact target `ViewContractRef`.

Revision publication or job preflight fails when:

- a source is missing or belongs to another organization;
- no registered materializer can produce the target view and schema version;
- required columns or images are unavailable;
- label spaces conflict without an explicit mapping;
- the selected deduplication, sampling, or missing-data policy is absent;
- current source data cannot satisfy the target view contract.

These failures are visible on the revision and in Task Tracker. There is no
fallback to another view contract, schema version, or storage path.

### 4.5 Composition and provenance

Collection publication is definition-only:

1. resolve the active ordered member identities;
2. pin the Collection definition version and deterministic filter, mapping,
   and sampling rule identities;
3. validate the exact target view contract;
4. persist the immutable Revision record and optional lightweight definition
   manifest;
5. publish only after the definition record is durable.

Publication does not scan, merge, or archive member samples. Runtime row
provenance is derived from current Dataset state plus namespaced sample
identity. Publication failure leaves the previous ready Revision usable.

### 4.6 Classify/read contract

The combined Collection classify page reads one explicit immutable Revision
through an SC data-provider collection scope:

```text
POST /api/v1/sc/data/collections/{collection_id}/revisions/{revision_id}/query
GET  /api/v1/sc/data/collections/{collection_id}/revisions/{revision_id}/events
```

`ScDataScope(kind="collection")` resolves the Revision members and opens their
current storage at workbench/runtime start. The user chooses one or more
members; table, gallery, global filters, sampling, annotations, training, and
prediction use that selected-member union. The map and wafer geometry use one
explicitly selected active member because different inspections cannot share a
single physical map. A disposable LazyFrame/Arrow union may be rebuilt as a
cache, but is never retained as Revision data.

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
`RuntimeDataSourceRef`. Dataset inputs open one `DatasetStorageAgg`; Collection
Revision inputs resolve a ready, immutable definition and current member data. Generic runtime hosts
remain source-agnostic; the registered SC runtime module owns source loading
and collection prediction fanout.

For train-and-predict, the same revision drives both phases. The visible SC
1,000-samples-per-class training cap is applied after collection membership and
workflow filters, ordered by stable `row_key`. Prediction retains the full
original revision scope, including rows held out of training.

Prediction output is keyed by `row_key`. A Collection writeback adapter resolves
the row's physical member identity in bulk, partitions results by physical
source Dataset, and calls each source `DatasetStorageAgg.write_predictions`.
Predictions consequently remain visible from standalone member datasets. The
job retains its Collection Revision and selected-member provenance even though result rows are
owned by physical source storage.

The Revision stores member and rule identity. Runtime row provenance is derived
from the current Dataset state at execution start and namespaced sample
identity; no retained full provenance sidecar or copied member union is
created.

## 5. Collection UI

Use a separate route and resource page:

```text
/dataset-collections
/dataset-collections/:id
```

List datasets and collections together on the top-level Data surface only if
each row has a clear `Dataset` or `Collection` badge. Do not make a collection
look like a physical dataset.

Collection Detail uses these contextual sections:

```text
Data | Models | Revisions | Activity
```

`Classify ↗` is a direct workspace action rather than an intermediate detail
tab.

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
6. Publish the first Revision after the successful member batch. Enable
   `Open collection` only when that Revision is ready; keep every imported
   Dataset independently openable even if another import or publication fails.

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
/dataset-collections/:collectionId/revisions/:revisionId/classify
```

The page reuses the SC dataset workbench and opens the Revision without a fake
representative Dataset route parameter. The user selects the participating
Revision members and one active member for the map. Each member remains
independently openable through the existing Dataset route. Training and
prediction use the same `revisionId` and selected member IDs.

- Table, gallery, filters, distribution, sampling, drafts, bulk annotation,
  training, and prediction use the selected-member union.
- The map and geometry use exactly one active selected member. Changing the
  active map member never changes the union selection implicitly.
- Patch/review image requests use each row's source inspection, wafer, dataset,
  and sample identity instead of the route's representative dataset.
- Selection and annotation drafts use `row_key`. The UI may display
  `defect_id`, inspection, wafer, lot, and member name, but none of those
  display fields is used as a collection row key.
- `Open dataset` on every source opens the existing standalone route. A
  collection never replaces or redirects that route.
- Train and Predict require an explicit ready Revision. Member Dataset content
  and upstream-field changes are picked up dynamically without publishing
  another Revision.

For MVP, “any composition” means any ordered set of already imported physical
datasets compatible with one exact target view contract. Arbitrary row slices,
weights, joins, and overlapping filters remain Phase 6 until their DSL and
failure semantics are accepted.

### Data

- target view contract and schema version;
- current definition version;
- latest ready Revision with current member sample and label counts;
- compatibility/readiness state;
- source count and manual/rule-managed state;
- last successful publication and latest error.

#### Member sources

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

The page shows when the mutable head differs from the latest ready Revision.
Linking, unlinking, reordering, or editing composition settings increments
`definition_version`; none of those operations mutates an existing revision.
An empty head remains in the Data section with a visible `no_active_members`
readiness reason and a `Link datasets` action.

### Revisions

Show immutable Revision number, trigger, definition version, ordered members,
rules, status, creator, time, and jobs using the Revision. Current counts are
resolved from the selected members rather than stored on the Revision. A
Revision can be inspected or used for training, but never edited.

### Models

The section shows the default Model, coverage, training and prediction jobs,
and candidate Models. The user selects a ready Revision. “Latest” may be a UI
label, but the submitted request always contains a concrete Revision ID and,
when scoped, explicit member IDs. Dataset content changes do not require
another Revision.

### Activity

Show the active membership rule, five-minute discovery state, recent automation
runs, admission failures, prediction coverage, and retry actions alongside
manual Collection activity. Editing a rule never rewrites an existing
Revision.

## 6. Automated Collection Publication

Interactive membership batches and typed membership rules share one Revision
publication contract. A successful manual batch, Discovery run, or Backfill
publishes at most one Revision after all accepted membership changes are
applied. The Revision records the resulting member and rule definition only.

### 6.1 Rule evaluation

One internal Prefect deployment evaluates all active rules every five minutes.
Rules are versioned, organization-scoped, and target exactly one Collection,
Source connector, and Import profile. Provider descriptors own the allowed
fields, types, and operators. The product does not expose a generic Sensor,
subscription, trigger/action builder, or collection-specific YAML registry.

```text
five-minute poll
      |
      v
active typed rule -> source discovery -> import/admit members -> publish Revision
```

Every upstream record that matches the rule is processed through bounded
pagination and batching without a hidden result cap. A failed record keeps its
own error and retry state; successful records can still contribute to the one
Revision published by that run.

### 6.2 Publication and idempotency

Publication is idempotent for the resulting definition. If member identities,
order, rules, and mappings are unchanged, the run returns `unchanged` and does
not create an indistinguishable Revision. Dataset row, annotation, prediction,
or upstream-field changes are not definition changes and therefore never
create an `Update available` state.

If the Collection head changes concurrently while a run is resolving, the run
fails with `definition_changed`; it does not publish a mixed definition.
Backfill fixes the rule version at launch and uses an independent cursor. It
may execute in internal windows, but those windows are not business
Partitions and do not publish separate Revisions.

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

There is no Collection `update-status` or `refresh` endpoint. Dataset Revision
publication and upstream value changes do not alter a Collection Revision and
do not require a compatibility endpoint. Collection Revision publication is
driven by a successful manual membership batch, Discovery run, or Backfill;
unchanged member/rule definitions return `unchanged`.
`POST /revisions` is the publication boundary used by those workflows, not a
user-facing action for manually versioning member data.

Dataset summary, import batches/source resolution, and additional combined
Collection annotations/query/events described elsewhere in this document are
planned extensions.

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

The lightweight Collection Revision definition uses the following shape; a
runtime resolves current member data into its operation-specific data-plane
input:

```json
{
  "collection_id": "col_123",
  "collection_revision_id": "colrev_7",
  "definition_version": 4,
  "members": [
    {
      "member_id": "member_1",
      "source_dataset_id": "dataset_1",
      "position": 0,
      "filter_version": "sha256:...",
      "mapping_version": "sha256:...",
      "sampling_version": "sha256:..."
    }
  ]
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

The module depends on typed Dataset, materializer/catalog, source-discovery,
and Task Tracker ports. It does not import sibling repositories or ORM
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
and remain unaware of Collection persistence details. The Collection module
implements Revision definition resolution and provenance-aware prediction
writeback behind ports. Runtime services receive a job-scoped data-plane
manifest built from current member data.

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
Revisions remain openable in classify even when the mutable Collection head is
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
- implement immutable Revision definition resolution;
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
- resolve current selected-member data through the data-plane manifest boundary;
- add provenance-aware prediction writeback to physical member datasets;
- add collection Train/Predict UI and task views.

### Phase 5: Automated Collection Publication

- add typed membership rules backed by Source connector and Import profile
  descriptors;
- evaluate active rules through the five-minute discovery deployment;
- publish at most one Revision per Discovery or Backfill run;
- expose discovery, admission, retry, and prediction-coverage state in the
  Collection and Task Tracker UI.

### Phase 6: Advanced Composition

- introduce a versioned filter AST;
- add explicit label mapping, deduplication, sampling, and weighting policies;
- add source adapters for event-derived dynamic membership if required.

Do not include Phase 6 behavior implicitly in the static collection phases.

### Management UI behavior

- Dataset Detail opens on the persisted dataset contract. Training and
  prediction are embedded sections of that page, so they must not render a
  second page header or refetch the selected dataset merely to label the form.
- Collection Detail presents the mutable definition and latest ready Revision
  as separate states. When they differ, the pending head change is visible and
  reviewing the older Revision identifies its Revision number explicitly.
- Management tables keep stable column widths and horizontal scrolling on
  compact screens. Below the application breakpoint, the global navigation
  collapses to its icon rail so page content retains usable width.

## 10. Required Verification

- backend: repository/service/route tests, organization-isolation tests,
  Revision concurrency tests, import-source ambiguity tests, Revision contract
  tests, and `make generate` plus `make test`;
- frontend: component tests, mock E2E for manual and rule-managed Collection flows,
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
  Revision publication, training, and prediction until a source is linked;
- collection training/prediction: a smoke test proving two datasets with
  different storage modes can materialize the same exact view contract, train
  from the recorded revision, predict the full revision scope, and write back
  through provenance;
- failure semantics: tests for one failed source import, one failed source
  annotation write, changed definition during Revision publication, and deletion
  of a referenced source.

## 11. MVP Decisions and Open Extensions

The implemented MVP makes these explicit choices:

1. a Collection Revision fixes member identity, order, rules, and mappings, but
   always resolves current member Dataset and upstream data;
2. composition is whole-dataset concatenation with `keep_all` and `fail` as
   required request values; non-empty filter, mapping, and sampling specs are
   rejected;
3. member datasets must expose the exact same ordered label space;
4. Collection prediction results are written through to the physical member
   Datasets while the job records Revision and selected-member provenance;
5. a successful manual batch, Discovery run, or Backfill publishes at most one
   Revision, and an unchanged definition publishes none;
6. member Dataset or upstream-field changes never create an update-available
   state and never require republishing the Revision;
7. Collection classify supports a selected-member union for table/gallery/
   filter/annotation/job operations and exactly one active member for the map;
8. source deletion is rejected while the accepted membership and Revision
   retention rules still reference the Dataset;
9. an empty Collection may remain a Draft, but it cannot publish an empty
   Revision or run classify, training, or prediction.

Summary freshness, advanced transform DSL semantics, and richer multi-source
annotation conflict handling remain planned extensions. They must not weaken
the Revision identity/current-data boundary above.
