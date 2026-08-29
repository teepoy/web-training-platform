# TODO: Reuse Visual List Controls and Align Resource Features

## Progress

- **Overall status:** Complete.
- **Completed intermediate slices:** removed the duplicate shared Dataset list
  surface; model management and Dataset/Collection model selection now use one
  model-search surface; Dataset, Collection, and Library list filters now share
  one responsive filter bar and remote-list state contract; job histories and
  Collection lists share status/list presentation; training and prediction can
  select either resource kind and pin the latest ready Collection revision;
  SC lookup behavior is centralized; reusable table-filter controls moved to
  shared ownership; and misleading `Sc*`/`Dataset*` visual component names were
  retired without compatibility aliases.
- **Verification:** 518 frontend unit tests, `make lint`, and the production Web
  build pass. Rendered Storybook review covers model management/picker, filtered
  Collection targets, and remote-list empty/error states.

This document records repeated visual/list behavior and dataset-versus-collection
feature gaps in the current web application. It is an audit and proposed cleanup
only. No component extraction, renaming, or product-flow change should begin
until the intended shared contracts and migration order are reviewed.

## Current Finding About Model Search

The earlier observation that model search works only for datasets is no longer
fully true:

- `apps/web/src/features/models/presentation/components/RemoteModelPicker.vue`
  supports both `dataset` and `collection` model sources.
- `apps/web/src/features/dataset-collections/presentation/pages/DatasetCollectionDetailView.vue`
  uses that picker when assigning a collection's default model.
- `apps/web/src/features/prediction/presentation/pages/PredictionJobsView.vue`
  also uses the same picker.

The remaining problem is inconsistent reuse and resource parity. The model list
and model picker duplicate search/filter/table behavior, and the training and
prediction forms still expose dataset-only targets even though their generated
API request contracts support `collection_id` and `collection_revision_id`.

## Resolved Reuse Decisions

### Model search

Model management and model selection will use one shared model-search surface:

- one query/state composable for keyword, source type, creator, compatibility,
  pagination, sorting, filter count, and reset behavior;
- one filter presentation and one result-row/table presentation;
- explicit `management` and `selection` modes for the few actions that differ;
- Dataset and Collection compatibility supplied as typed constraints, not as
  separate picker implementations.

The shared surface remains owned by the models feature because it represents
model-domain behavior. Resource pages configure it and handle binding actions.

### Table filters

Use a standardized filter experience built from reusable layers, not one
monolithic table component:

- a domain-neutral resource filter-bar shell and remote-list state composable
  for search debounce, active count, clear, pagination, sorting, and reset;
- typed field descriptors and feature-owned query mapping for each resource;
- a separate SC filter controller because distinct-value/range lookup and the
  virtual sample table have materially different scale and semantics;
- consistent visual language for filter triggers, applied state, loading,
  errors, clearing, and responsive layout across both layers.

### Visual implementation priority

After consolidating the duplicate Dataset list surface, implement in this order:

1. Shared model search and selection.
2. Shared resource filter shell and remote-list state, proven on Dataset and
   Collection lists.
3. A shared remote-list presentation shell covering pagination plus loading,
   error, no-results, and truly-empty states.
4. Shared semantic status badges and status-label mapping.
5. Shared row/bulk action-menu presentation with feature-owned permissions and
   commands.
6. Import/export flow consistency after the preceding primitives stabilize;
   these workflows retain domain-specific bodies and registration.

Each completed slice must be shown for visual review with representative
rendered states. At minimum, show model management and picker modes, Dataset and
Collection list filtering/pagination/empty states, and any affected SC filter
surface before the slice is considered accepted.

These extractions preserve existing routes, API behavior, permissions, and
workflows. Compatibility aliases may bridge renamed components temporarily; no
stored-data backfill is required.

## Candidate Inventory

### P0: Two dataset-list surface implementations have diverged

Files:

- `apps/web/src/shared/datasets/surface.ts`
- `apps/web/src/features/datasets/application/surface.ts`
- `apps/web/src/features/datasets/presentation/pages/DatasetListView.vue`

Both surface modules define `useDatasetListSurface` and substantially duplicate
column construction, action menus, selection behavior, and access checks. The
feature-local version has accumulated additional sorting, creator, view-type,
width, and permission behavior while the shared version and its tests remain in
place. `DatasetListView.vue` imports the feature-local copy.

Proposed direction:

- Select one canonical owner and merge the supported behavior into it.
- Preserve domain-specific column and action extension points rather than
  copying the complete surface again.
- Move or rewrite the existing shared-surface tests so they cover the active
  implementation.
- Remove the second implementation only after all importers are migrated.

Completed: the feature-owned implementation is now the sole Dataset list
surface. Its tests moved beside the active composable, the stale shared export
and duplicate implementation were removed, and the shared row contract gained
the typed `view_types` field needed to eliminate the remaining `any` cast.

### P0: Resource list filter bars repeat the same visual and state behavior

Files and features:

- `apps/web/src/features/library/presentation/pages/LibraryWorkspaceView.vue`
  - Search, creator scope, active-filter count, clearing, URL query state, and
    dataset/collection tab coordination.
- `apps/web/src/features/datasets/presentation/pages/DatasetListView.vue`
  - A second search/creator filter bar when used outside the library workspace.
- `apps/web/src/features/dataset-collections/presentation/pages/DatasetCollectionListView.vue`
  - A separate creator filter, remote pagination, sorting, selection, table,
    and empty-state implementation.
- `apps/web/src/features/models/presentation/pages/ModelsView.vue`
  - Search, source type, creator scope, filter count, clearing, pagination, and
    sorting.
- `apps/web/src/features/training/presentation/pages/TrainingJobsView.vue`
  and `apps/web/src/features/prediction/presentation/pages/PredictionJobsView.vue`
  - Nearly matching job-history search, status, creator, clear, pagination, and
    sorting flows.
- `apps/web/src/features/task_tracker/presentation/pages/TaskExplorerView.vue`
  - The same pattern with task-kind and status fields.
- `apps/web/src/features/automations/presentation/pages/AutomationsView.vue`
  - A similar search/status/work-kind bar, but without the same filter count and
    clear behavior.

Repeated behavior includes the filter row layout, 250 ms search debounce,
active-filter count, clear action, page reset after filter/sort changes, remote
pagination sizes, controlled sort state, selection reset, and responsive
layout. Small variations have already caused inconsistent controls and behavior.

Proposed direction:

- Add a domain-neutral filter-bar shell with slots for resource-specific fields,
  a consistent clear action, count presentation, and responsive layout.
- Add a small remote-list state composable for debounce, pagination, sorting,
  and reset rules.
- Keep query parameter construction and domain filter meanings in each feature;
  do not create one oversized component that owns every resource's filters.
- Define whether `LibraryWorkspaceView.vue` or its embedded resource list owns
  search and creator state, then use one owner instead of parallel state paths.

Completed: `ResourceFilterBar` now owns the shared search/creator/clear/action
layout, while `useRemoteListState` owns debounce, pagination, sorting, total,
and selection-reset mechanics. Dataset and Collection standalone lists consume
the same contracts, and the Library remains the sole filter-state owner when
those lists are embedded. Focused tests cover debounce, filter/page resets,
sorting, conditional pagination, the compatibility search selector, and the
shared action slot.

### P0: Model browsing is implemented twice

Files:

- `apps/web/src/features/models/presentation/pages/ModelsView.vue`
- `apps/web/src/features/models/presentation/components/RemoteModelPicker.vue`
- `apps/web/src/features/dataset-collections/presentation/pages/DatasetCollectionDetailView.vue`
- `apps/web/src/features/prediction/presentation/pages/PredictionJobsView.vue`

`ModelsView.vue` and `RemoteModelPicker.vue` independently implement model
keyword search, source-type selection, creator filtering, active-filter count,
clearing, remote pagination, table columns, and source labels. The picker adds
selection and compatibility constraints; the management page adds management
actions. These are modes of the same model-search surface rather than unrelated
implementations.

Proposed direction:

- Extract a model-search query/state composable shared by the page and picker.
- Reuse a model filter bar and result-table presentation with explicit
  management and selection modes.
- Retain `compatibleViewIds` (or a typed successor) as a picker constraint.
- Keep management actions in the models feature and resource-specific binding
  actions in their owning dataset/collection flows.
- Preserve the current collection support instead of creating a second
  collection-only model picker.

Completed: `ModelSearchSurface` and `useModelSearch` now serve both management
and selection modes. The existing `RemoteModelPicker` is a compatibility-thin
wrapper, and Dataset/Collection source compatibility remains a typed query
constraint. Management and Collection-compatible picker stories were rendered
and reviewed as the representative states for this slice.

### P1: Dataset and collection list experiences are asymmetric

Files:

- `apps/web/src/features/library/presentation/pages/LibraryWorkspaceView.vue`
- `apps/web/src/features/datasets/presentation/pages/DatasetListView.vue`
- `apps/web/src/features/dataset-collections/presentation/pages/DatasetCollectionListView.vue`
- `apps/web/src/shared/components/datasets/dataset-table/DatasetTable.vue`
- `apps/web/src/shared/components/bulk-selection-toolbar/BulkSelectionToolbar.vue`
- `apps/web/src/shared/components/creator-scope-select/`

The dataset list uses the shared dataset table and dataset surface, while the
collection list directly assembles its own `NDataTable`, selection, pagination,
empty state, and row interactions. Search behavior also differs depending on
whether each list is embedded in the library workspace.

The collection creation flow loads every dataset in repeated 200-item pages and
then uses a local filterable select. This should be evaluated against a reusable
remote dataset/resource picker so large installations do not need to load the
entire catalog before the user can search.

Proposed direction:

- Reuse existing `CreatorScopeSelect` and `BulkSelectionToolbar`; they are
  already correctly shared.
- Generalize the useful table behavior for both dataset and collection lists.
- Give embedded and standalone lists one documented controlled/uncontrolled
  filter contract.
- Replace load-all selection only after the backend search and compatibility
  requirements for a remote resource picker are confirmed.

Completed for presentation/state parity: Dataset and Collection filtering now
has one controlled/standalone contract; Collection and job tables use the
shared `RemoteListTableShell` for load errors, true empty states, filtered
no-results states, and pagination presentation. The existing Dataset page shell
continues to preserve its established full-page loading behavior while its
filter, pagination, sorting, and selection resets use the same shared state.
Replacing the Collection creation flow's load-all picker remains intentionally
separate because it changes query/product behavior rather than list visuals.

### P1: Training and prediction target selectors are dataset-only

Files and contracts:

- `apps/web/src/features/training/presentation/pages/TrainingJobsView.vue`
- `apps/web/src/features/prediction/presentation/pages/PredictionJobsView.vue`
- `apps/web/src/generated/orval/models/createTrainingJobRequest.ts`
- `apps/web/src/generated/orval/models/runPredictionRequest.ts`

Both job forms model and validate only `dataset_id`. The generated request
contracts also accept `collection_id` and `collection_revision_id`, and job
response/list contracts expose collection fields. The frontend therefore does
not expose the full resource targeting already represented by the API.

Proposed direction:

- Define a shared dataset-or-collection resource selector contract with an
  explicit resource kind, identifier, optional revision, display name, and view
  compatibility information.
- When a mutable Collection is selected, training or prediction pins its current
  ready revision at job submission. The submitted job never silently moves to a
  later membership revision.
- Update job history columns, retry actions, route links, and empty/deleted
  labels together; changing only the create form would leave the flow
  inconsistent.
- Keep this parity change separate from the visual extraction so API/product
  decisions are reviewable independently.

Completed: training and prediction now consume one typed resource-target
selector. Dataset requests contain only `dataset_id`; Collection requests
contain `collection_id` plus the latest ready `collection_revision_id`, and the
UI states explicitly which snapshot will be pinned. Both histories render a
shared linked target label and semantic status badge. Focused tests cover latest
ready revision selection and mutually exclusive request fields.

### P1: SC filter controls share components but duplicate orchestration

Files and features:

- `apps/web/src/features/sc/presentation/components/ScRangeFilterMenu.vue`
- `apps/web/src/features/sc/presentation/components/ScSetFilterMenu.vue`
- `apps/web/src/features/sc/presentation/components/ScTextFilterMenu.vue`
- `apps/web/src/features/sc/presentation/components/ScFilterPopover.vue`
- `apps/web/src/features/sc/presentation/components/ScGlobalFilterQueryBuilder.vue`
- `apps/web/src/features/sc/presentation/components/ScDatasetGlobalFilterControl.vue`
- `apps/web/src/features/sc/presentation/components/ScSampleTableTanStack.vue`
- `apps/web/src/features/sc/presentation/components/ReviewSamplingModal.vue`
- `apps/web/src/features/sc/presentation/components/ScPredictionExportPlugin.vue`
- `apps/web/src/features/sc/presentation/components/InspectionQuad.vue`

SC already has reusable range, set, text, and global-query visual components.
The remaining duplication is the controller behavior around distinct-value
search, per-rule caches, numeric ranges, loading/error state, filter-model
translation, and event forwarding.

Proposed direction:

- Extract a typed SC-domain filter catalog/controller composable that owns
  option searches, range loading, caching, and error state.
- Keep the existing focused menu components and let each consuming screen own
  its workflow-specific submission behavior.
- Do not merge SC field/filter semantics into the generic resource-list filter
  bar; these are separate abstractions at different layers.

Completed: `useScFilterLookupController` now owns stale-response protection,
distinct-value results, numeric-range caching, per-rule loading/error state,
and reset behavior. Both the Dataset Global Filter and Inspection workspace use
it while retaining their workflow-specific loaders and error reporting. Tests
cover stale searches and keyed range failures; the specialized SC tables remain
unchanged.

### P2: Shared visual primitives are dataset-named despite broader use

Files:

- `apps/web/src/shared/components/datasets/dataset-page-shell/`
- `apps/web/src/shared/components/datasets/dataset-toolbar/`
- `apps/web/src/shared/components/datasets/dataset-table/`

Some of these primitives express domain-neutral page, toolbar, and remote-table
behavior and are already used outside a strict dataset-only context. Their
names discourage intentional reuse and make it unclear which behavior is truly
dataset-specific. `DatasetToolbar` currently provides little beyond a title and
layout slot, so it may not justify a separate dataset abstraction.

Proposed direction:

- Classify each primitive as resource-generic or genuinely dataset-specific.
- Rename or replace only the generic primitives, using temporary re-exports if
  needed to avoid a disruptive all-at-once import rewrite.
- Keep dataset-specific columns, permissions, and actions outside the generic
  table/shell package.

Completed: domain-neutral `DatasetPageShell` and `DatasetToolbar` became
`ResourcePageShell` and `ResourceToolbar`; the Dataset table, row actions, and
Dataset list surface retain their domain names. SC-only visual components now
use concise names inside the SC namespace, while the reusable table-filter
popover, range menu, and set menu live under shared ownership.

## Explicit Non-Candidates

- `CreatorScopeSelect` and `BulkSelectionToolbar` are already reusable shared
  controls; new list surfaces should consume them rather than replace them.
- The existing collection use of `RemoteModelPicker` is valid reuse and should
  not be duplicated with a collection-specific copy.
- SC's virtualized, column-filtered sample tables should not be forced through
  the same wrapper as ordinary remote `NDataTable` resource lists.
- Domain columns, permissions, row actions, API parameters, and filter meanings
  should remain with their owning features even when their visual shells and
  list-state mechanics are shared.
- Small one-off detail tables do not need a wrapper merely because they use
  `NDataTable`; extraction should target repeated behavior, not component-name
  counts.

## Proposed Execution Order

1. Consolidate the two `useDatasetListSurface` implementations and their tests.
2. Define the minimal generic filter-bar and remote-list state contracts, then
   migrate dataset and collection lists as the first paired example.
3. Extract shared model search state and result presentation from `ModelsView`
   and `RemoteModelPicker`, preserving collection compatibility filtering.
4. Migrate the matching training/prediction history filters and other resource
   pages incrementally; do not perform a repository-wide mechanical rewrite.
5. Add dataset-or-collection target selection as a separate feature change,
   pinning the Collection's current ready revision at job submission.
6. Extract the SC-specific filter controller without coupling it to generic
   resource-list filters.
7. Generalize or retire misleading `Dataset*` shared primitive names after the
   consumers demonstrate the stable boundary.

## Acceptance Criteria

- One active implementation owns dataset-list surface behavior and its tests.
- Repeated resource filter bars share layout, clear/count behavior, debounce,
  pagination reset, controlled sorting, and responsive rules without losing
  domain-specific filters.
- Model management and model picking use the same search/filter/result
  primitives, including dataset and collection sources.
- Dataset and collection lists have consistent embedded/standalone filter,
  selection, pagination, loading, error, empty, and row-interaction behavior.
- Training and prediction can target every resource kind intentionally
  supported by their API contracts, including explicit collection revision
  behavior, or the unsupported contract fields are removed through a separate
  API decision.
- SC screens share distinct-value/range lookup and filter-controller behavior
  while retaining their specialized table implementation.
- Shared component names communicate their real ownership and scope.
- Focused component/composable tests cover filter clearing, debounce, page and
  selection reset, source compatibility, collection revisions, sorting, and
  responsive rendering.
- `make lint`, `make test-web`, and `make build-web` pass after implementation.

## Before Implementation

The model-search, filter-reuse, visual-priority, and Collection job-revision
decisions are approved. Implement the work in small backward-compatible
feature-paired changes so shared abstractions are proven by real consumers, and
present the rendered result for review after every slice.
