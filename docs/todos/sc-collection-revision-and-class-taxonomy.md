# TODO: SC Collection Revision and Class Taxonomy

## Status

- **Overall status:** Complete.
- Recorded before implementation on 2026-08-30.
- Completed and regression-verified on 2026-08-30.

## Accepted Product Semantics

1. Use **Collection Revision** everywhere. The feature has not been released,
   so no user-facing or transport compatibility alias is required for the
   discarded terminology.
2. A Collection Revision fixes its member identities, ordering, and rules. It
   does not freeze member Dataset contents. Classify, training, and prediction
   always resolve the latest Dataset and upstream values.
3. Collection Classify lets the user select multiple Revision members. The map
   uses one explicitly selected active inspection while table, gallery,
   filters, annotation, and jobs use the selected-member union.
4. The current SC automation partition is exactly `layer_id + device`; remove
   the alternate dimension selector and recipe branch.
5. Source discovery imports every matched source record and every row. Remove
   `max_records_per_run` and `max_rows_per_dataset`; use pagination/batching
   without truncation.
6. The current version may restrict Collection members to compatible sparse SC
   Datasets with an explicit inspection identity. `db_full` remains available
   as a single-Dataset workflow.
7. Remove the incorrect 300,000-row Collection Classify guard. A future guard,
   if needed after measurement and correct counting, is 10,000,000 rows.

## Class Mapping Contract

- Add one canonical SC class-mapping contract that maps raw integer
  `class_number` values to user-facing class names.
- Raw integer values remain the query, filter, transport, and export identity;
  display names are presentation metadata.
- The shared resolver must cover map legends, tables, galleries, filters,
  sampling controls, tooltips, and other frontend class-number displays.
- Unknown values display their raw number and never silently map to another
  class.
- `class_number` is upstream source data. Annotation labels and model output
  labels remain separate concepts unless a later explicit decision unifies
  them.

Ownership is resolved: the mapping is platform-wide. The first implementation
uses one shared frontend SC registry/module, with no database table, API,
organization scope, connector scope, or per-Dataset copy. Mapping changes ship
with the frontend release. All frontend callers must use that registry rather
than carrying private literal maps. Add a read-only platform endpoint only if a
future non-web consumer actually needs the display names.

## Confirmed Stale-Metadata Defect

Before the correction, annotation create/update/bulk paths called
`DatasetService.merge_label_space()`. That method computed an additive set
union and never removed labels that were no longer used.

A temporary integration reproduction performed these steps:

1. Create a Dataset with label space `["current"]`.
2. Annotate its only sample as `"temporary"`.
3. Overwrite that same annotation as `"current"`.
4. Read the Dataset metadata.

The annotation query correctly returned only `"current"`, while Dataset
metadata incorrectly remained `["current", "temporary"]`. The exact
reproduction failed deterministically in 3.80 seconds; a second probe confirmed
that annotation persistence itself contains only the overwritten current value.
The temporary probe files were deleted after execution.

## Implemented Correction

- Stopped deriving persistent Dataset taxonomy metadata by unioning observed
  annotation values.
- Configured class names/mappings remain explicit contract data.
- Used-label counts are computed dynamically from current annotations at Dataset or
  selected Collection-member scope.
- Training readiness uses the dynamic current counts, not a Revision field
  or an additive metadata list.
- Overwriting or deleting the final use of a label immediately disappears
  from observed counts without rewriting unrelated Dataset metadata.

## Completed Result

- The Collection transport and UI use Revision-only terminology and consume
  `revision.members` directly, with no compatibility alias or Dataset-Revision
  update/refresh flow.
- A Revision stores member and rule identity only. Classify and jobs resolve
  current Dataset and upstream data; no member union is copied or retained.
- Collection Classify provides a Revision-member multiselect and one active map
  inspection. Table, gallery, filters, annotation, readiness, training, and
  prediction use the selected-member union; map and geometry use the active
  member.
- Train-and-predict carries explicit `collection_member_ids`. With no user
  filter it sends no duplicate member predicate; a filtered workflow resolves
  row keys within the selected-member scope.
- The incorrect 300,000-row gate and its API/configuration/client plumbing were
  removed without adding an unmeasured replacement limit.
- One shared frontend SC registry owns raw integer `class_number` display
  names. Raw integers remain query/filter/transport/export identity and unknown
  values display their raw number.
- Annotation write paths no longer add observed labels permanently to Dataset
  taxonomy metadata. Current label counts are derived from current annotations,
  including selected-member Collection readiness.
- Source discovery streams every match in bounded batches instead of enforcing
  a product cap or eagerly collecting the complete match set.
- The migration rejects legacy non-device partitions before changing schema;
  it never silently reinterprets `recipe_id` as `device`.

## Verification

- `make lint` completed successfully: web i18n literals, Ruff, and Prettier
  all passed.
- `make test-web`: 99 test files and 525 tests passed.
- Focused `useReclassifyPage.spec.ts`: 19 tests passed.
- `make build-web` passed.
- Focused mock Playwright Collection Revision/classify flow: 1 test passed.
- Full `make test-e2e`: 50 tests passed.
- `make test`: 1,078 tests passed, 15 skipped, and 1 xpassed; generated OpenAPI
  synchronization passed.
- Full API Pyright completed with 0 errors, and Ruff was clean.
- `make generate` and `make graphify-check` passed.
- The Alembic migration applied successfully to the development PostgreSQL
  database.
- `git diff --check` passed.
