# Dataset Summary, Collection, and Dynamic Collection

Status: draft proposal
Date: 2026-07-31

## 1. Scope

This proposal covers three related product capabilities:

1. a useful Dataset Summary view;
2. a Dataset Collection, also called a virtual dataset, that can train on data
   from multiple datasets;
3. a Dynamic Dataset Collection whose immutable revisions are refreshed by a
   sensor or cron schedule.

The proposal does not make a collection another physical `DatasetORM`. A
dataset owns samples and storage; a collection owns a composition rule and
immutable revisions. Keeping these concepts separate avoids inventing a third
`storage_mode` and preserves the existing `DatasetStorageAgg` boundary.

This document is intentionally a draft and does not amend `CORE_DESIGNS.md`.
The decisions in the final section must be accepted before implementation.

## 2. Product Model

### 2.1 Terms

| Term                | Meaning                                                                                                               |
| ------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Dataset             | A physical platform dataset with one explicit `storage_mode`.                                                         |
| Collection          | A reusable logical definition containing one or more dataset sources and explicit composition rules.                  |
| Collection revision | An immutable, resolved snapshot of a collection definition and its source manifests. Training consumes this resource. |
| Static collection   | Membership changes only through an explicit user edit and revision creation.                                          |
| Dynamic collection  | The same collection model with one or more refresh bindings that request new revisions.                               |
| Refresh run         | One observable attempt to resolve a collection definition into a revision.                                            |

“Dynamic” is behavior, not a second storage type. A collection can become
static or dynamic by adding or removing refresh bindings.

### 2.2 Core invariant

Training never consumes a mutable collection head.

```text
collection definition
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
training job
```

The UI may offer “Refresh and train”, but it must perform and expose two
operations: create a successful revision, then submit training with that
revision ID. A job records the exact revision it used.

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
| `definition_version`                            | Monotonic optimistic-lock version.                          |
| `created_by`, `created_at`, `updated_at`        | Audit fields.                                               |

#### `dataset_collection_members`

| Field                                      | Notes                                                                        |
| ------------------------------------------ | ---------------------------------------------------------------------------- |
| `id`, `collection_id`, `source_dataset_id` | A source belongs to the same organization.                                   |
| `position`, `enabled`                      | Stable display/composition order.                                            |
| `filter_spec`                              | Versioned, validated filter AST; `{}` means an explicitly unfiltered source. |
| `label_mapping`                            | Explicit source label to target label mapping.                               |
| `sampling_spec`                            | Explicit include/weight/cap strategy; no implicit weighting.                 |

MVP should support whole-dataset membership first. Filter and sampling fields
are present in the contract only when their DSL and failure semantics are
specified; arbitrary SQL or Polars expressions are not accepted over HTTP.

#### `dataset_collection_revisions`

| Field                                                     | Notes                                                                                                 |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `id`, `collection_id`, `revision_number`                  | Immutable collection snapshot identity.                                                               |
| `definition_version`, `definition_hash`                   | Exact definition that was resolved.                                                                   |
| `target_view_contract`, `target_schema_version`           | Frozen compatibility boundary.                                                                        |
| `status`                                                  | `pending`, `ready`, or `failed`.                                                                      |
| `source_snapshot`                                         | Source dataset IDs, storage modes, manifest/version refs, filters, mappings, and source fingerprints. |
| `row_count`, `label_counts`                               | Revision summary when ready.                                                                          |
| `manifest_uri`, `provenance_uri`                          | Resolved collection manifest and row provenance sidecar.                                              |
| `trigger_kind`, `trigger_ref`, `created_by`, `created_at` | Audit and automation provenance.                                                                      |
| `error_code`, `error_detail`                              | Explicit failure result.                                                                              |

#### `dataset_collection_refresh_runs`

Tracks idempotency key, requested definition version, triggering event or
schedule run, state, timestamps, resulting revision, and error. Task Tracker
links to this record.

### 4.2 Compatibility rules

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

### 4.3 Composition and provenance

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

### 4.4 Training contract

Replace the assumption that every training input is a mutable `dataset_id`
with a typed source reference in a new API contract:

```json
{
  "data_source": {
    "kind": "collection_revision",
    "collection_id": "col_123",
    "revision_id": "colrev_7"
  },
  "trainer_id": "sc.resnet50.train.v1",
  "parameters": {}
}
```

A normal dataset uses:

```json
{
  "data_source": {
    "kind": "dataset",
    "dataset_id": "ds_123"
  }
}
```

The training job persists the full typed reference. Dataset-only callers may
use the existing endpoint during a documented migration period, but collection
training must not overload `dataset_id` with a collection ID.

The data-plane manifest needs a new schema version that can identify
`collection_revision` as its source and reference the provenance sidecar. Its
table payload still conforms to the exact existing view contract, so trainer
implementations do not become collection-aware.

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
Summary | Sources | Revisions | Train | Automations | Activity
```

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
Saving changes increments `definition_version`; it does not mutate an existing
revision.

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

## 6. Dynamic Collections

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

Suggested endpoints:

```text
GET    /api/v1/datasets/{id}/summary

POST   /api/v1/dataset-collections
GET    /api/v1/dataset-collections
GET    /api/v1/dataset-collections/{id}
PATCH  /api/v1/dataset-collections/{id}
DELETE /api/v1/dataset-collections/{id}

PUT    /api/v1/dataset-collections/{id}/members
GET    /api/v1/dataset-collections/{id}/summary

POST   /api/v1/dataset-collections/{id}/revisions
GET    /api/v1/dataset-collections/{id}/revisions
GET    /api/v1/dataset-collections/{id}/revisions/{revision_id}

POST   /api/v1/dataset-collections/{id}/refresh-bindings
GET    /api/v1/dataset-collections/{id}/refresh-bindings
PATCH  /api/v1/dataset-collections/{id}/refresh-bindings/{binding_id}
DELETE /api/v1/dataset-collections/{id}/refresh-bindings/{binding_id}

POST   /api/v1/training-jobs
```

`PUT /members` carries `expected_definition_version` and atomically replaces
the ordered definition. A version mismatch returns `409`; partial membership
updates do not leave a half-valid collection.

All new request/response DTOs originate in route/schema code and are exported
through `make generate`. `openapi/openapi.yaml` is not edited manually.

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
training module accepts a typed data-source port and remains unaware of
collection persistence details. Runtime services receive only the versioned
data-plane manifest.

Frontend code lives under:

```text
apps/web/src/features/dataset-collections/
```

Collection source editors, automation editors, and summary panels are
registered through descriptors where they are extension points. The app
registration barrel performs registration; pages do not add dataset-type
switch statements.

## 9. Delivery Plan

### Phase 1: Dataset Summary

- add the composed summary DTO/service/endpoint;
- add Summary and Samples tabs to the dataset page;
- add capability/readiness and storage-aware cards;
- add focused API, component, and route tests.

### Phase 2: Static Collection and Training

- add ORM models and Alembic migration;
- implement collection CRUD, atomic member editing, and compatibility checks;
- implement immutable revision resolution and collection manifest v2;
- change training submission to accept a typed data source;
- add collection list/detail/source/revision/train UI.

### Phase 3: Dynamic Collection

- harden sensor tenancy, auth, validation, and typed actions;
- register `refresh_dataset_collection.v1`;
- add sensor and cron bindings plus idempotent refresh runs;
- expose automation state in Collection and Task Tracker UI.

### Phase 4: Advanced Composition

- introduce a versioned filter AST;
- add explicit label mapping, deduplication, sampling, and weighting policies;
- add source adapters for event-derived dynamic membership if required.

Do not include Phase 4 behavior implicitly in Phase 2.

## 10. Required Verification

- backend: repository/service/route tests, organization-isolation tests,
  revision concurrency tests, manifest contract tests, `make generate`, and
  `make test`;
- frontend: component tests, mock E2E for static and dynamic collection flows,
  `make test-web`, and `make build-web`;
- route/user-flow changes: `make test-e2e`;
- all code changes: `make lint` first, followed by the narrowest relevant
  checks;
- collection training: a smoke test proving two datasets with different
  storage modes can materialize the same exact view contract and train from the
  recorded revision.

## 11. Decisions Required Before Implementation

1. **Revision retention:** prevent source deletion while referenced, or copy
   and retain all revision shards for a defined period.
2. **MVP composition policy:** whole-dataset concatenation only, or include a
   versioned filter/sampling DSL in the first release.
3. **Duplicate policy:** require users to choose `keep_all` or an exact
   deduplication key; there is no safe implicit choice.
4. **Label policy:** require identical label spaces in MVP, or require explicit
   per-source mapping.
5. **Refresh publication:** publish a new revision only when source
   fingerprints change, as proposed, or record every successful trigger as a
   distinct revision.
6. **Summary freshness:** define which mutations enqueue summary recomputation
   and whether users can request an on-demand refresh.
