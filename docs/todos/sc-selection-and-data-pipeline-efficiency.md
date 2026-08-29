# TODO: SC Selection and Data Pipeline Efficiency

## Batch Baseline

- Recorded before implementation at commit
  `83db1c1d50242b4086978e07918d80b62c4f7785`.
- **Overall status:** Complete. Multi-label selection, Collection-safe identity,
  linear uniqueness, bounded gzip transport, and the cross-pipeline audit are
  implemented and tested.

## Checkpoints

- [x] Add click-to-toggle multi-label legend selection while retaining the
  former scalar Legend event/property as a compatibility adapter.
- [x] Replace per-action full-selection sorting with linear, insertion-ordered
  uniqueness. The Arrow worker owns uniqueness through `Set`; downstream
  filters do not require ordering.
- [x] Make the Arrow map contract carry generated `map_id` explicitly. The
  previous `map_id AS defect_id` alias was removed; Collection members with
  repeated SC defect IDs therefore cannot collide in map selection.
- [x] Audit remaining frontend sorts: retained sorts operate on bounded display
  metadata (legend groups, filter options, labels, columns, or loaded page
  segments), not the full point selection.
- [x] Gzip SC query bodies above 4 KiB in capable browsers. The data provider
  rejects malformed gzip and enforces tracked 16 MiB compressed / 64 MiB
  decompressed limits; uncompressed clients remain compatible.
- [x] Complete the transport/backend identity audit and representative
  performance measurement.

## Requested Outcomes

1. Legend label selection supports selecting multiple labels at once.
2. The complete label-selection pipeline is traced and benchmarked. Operations
   such as unique, sort, materialization, copying, and client-side joins are
   retained only when their contract requires them.
3. Other SC data operations receive the same bounded complexity and allocation
   audit, including map, table, gallery, filter, selection, annotation, training,
   prediction, and export paths.
4. Large sample-identity selections use a bounded request representation rather
   than uncompressed JSON arrays when that materially reduces request size.
5. Filter and selection transport uses stable platform sample identity or an
   explicitly defined stable row index. SC `defect_id` must not be the selection
   identity because it is not globally unique across Collection members.

## Required Investigation

- Trace Legend selection through `InspectionQuad`, map/table/gallery state,
  query construction, SC data-provider SQL policy, annotation writes, workflow
  filters, prediction/export inputs, and Collection classify.
- Measure current time and allocation complexity with representative and maximum
  supported point counts. Do not infer `O(N log N)` solely from source shape.
- Identify every `sort`, `Set`/unique, array copy, serialization pass, and
  client/server reorder. For each, document the invariant it establishes and
  which owner can guarantee that invariant.
- Inventory every frontend and backend use of `defect_id`, upstream `sample_id`,
  platform `Sample.id`, `__row_index`, and local array index. Classify each as
  domain display identity, storage identity, stable query identity, or ephemeral
  presentation position.
- Compare compact selection contracts such as sorted integer ranges, roaring
  bitmap/binary payloads, compressed request bodies, server-side selection
  handles, and predicate-based selection. Choose only after measuring identity
  density, ordering, cache lifetime, retry semantics, and authorization needs.

## Compatibility and Failure Rules

- Existing single-label selection remains a valid interaction within the new
  multi-selection model.
- Collection classify must not merge rows that share a `defect_id` across
  inspections.
- Selection compression must preserve exact membership, ordering semantics where
  relevant, organization authorization, request retry behavior, and explicit
  size limits.
- A server ordering guarantee may replace client sorting only when it is part of
  the response/query contract and covered by tests.
- No implicit sample cap, truncation, or lossy selection representation is
  allowed.

## Acceptance Criteria

- Legend multi-selection behavior is specified, accessible, implemented, and
  tested across map, table, gallery, and clear/reset flows.
- Before/after benchmarks cover the selection hot path and any removed sort or
  unique operation.
- Every retained `O(N log N)` operation in audited hot paths has a documented
  contract reason, or is replaced with a measured lower-cost implementation.
- Selection/filter APIs use a Collection-safe stable sample identity contract;
  `defect_id` is used only as SC domain data where uniqueness is not assumed.
- Large selections have an explicit bounded transport contract with round-trip,
  malformed-input, authorization, and maximum-size tests.
- Frontend unit/widget tests, backend/data-provider tests, OpenAPI/protobuf
  artifacts where applicable, and performance checks pass.

## Decisions

- Multi-select uses plain click-to-toggle; selecting an already-selected label
  removes only that label.
- Map operations use materialized `map_id`, a unique row index within the
  current immutable workbench snapshot. Table/annotation operations use
  physical `row_key`, which resolves to platform `Sample.id` (and Dataset ID for
  Collection rows). Upstream SC `sample_id` and `defect_id` remain domain data.
- Gzip was selected over ranges/bitmaps because it preserves the existing exact,
  stateless, retryable JSON contract and remains O(N) even when selected map IDs
  are not sorted. Server-side handles would add state, expiry, and authorization
  semantics that this request does not require.

## Audit and Measurement

- The 300,000-row map is ordered once by backend `map_id`; the client no longer
  sorts the full selected set. Display-only sorts remain bounded to legends,
  columns, filters, labels, or the current page.
- Map and selection queries use `map_id`; table and gallery selection predicates
  use `row_key`; Collection annotation submission decodes `row_key` to the
  member Dataset plus platform `Sample.id`. SC `defect_id` remains in gallery,
  KLARF, upstream and domain filter paths where its domain meaning is required.
- A local Node 22 benchmark on the recorded baseline machine compared
  `Set + numeric sort` with insertion-ordered `Set`: at 10k / 100k / 300k IDs,
  measured times were 1.34/13.40/56.25 ms versus 0.38/3.34/33.19 ms. This is a
  representative microbenchmark, not an end-to-end browser performance claim.
- The same randomized 10k / 100k / 300k JSON identity bodies compressed from
  48,908/588,908/1,988,908 bytes to 22,985/273,308/953,470 bytes (about 2.1x).
  More locally ordered selections generally compress better.
