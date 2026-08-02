# SC Pipeline Performance Remediation Plan

Status: Implemented in code; local 300k/Compose acceptance completed
Recorded: 2026-08-01
Scope: SC import, sparse annotation, training/prediction materialization, and
the DuckDB SQL data provider

## Outcome

Make memory proportional to an explicit batch size instead of the inspection
row count. A 300k or 1M inspection must not make the API, data provider, or
runtime worker retain a full Python object graph, full image set, or duplicate
Arrow/Polars copies.

The process boundaries and browser contract do not change:

- the normal API remains the control plane;
- the SC SQL provider remains a separate service;
- browser data queries remain HTTP + read-only SQL + Arrow IPC;
- invalidation remains SSE;
- no Perspective or failure fallback is reintroduced.

This plan first fixes bounded execution in the current topology. Moving import
execution out of the API is a separate architecture decision and is not a
prerequisite for the bounded-streaming changes.

## Evidence from the live 300k run

The latest acceptance run reached these states before it was stopped:

| Measurement                               |                            Observed |
| ----------------------------------------- | ----------------------------------: |
| Direct API import                         |                            30.079 s |
| Import process RSS at completion          |                       1,618,132 KiB |
| Import process high-water RSS             |                       1,716,124 KiB |
| Preview-to-workspace E2E                  |                             1.6 min |
| Workspace cold load in that E2E           |                            61.211 s |
| API cgroup peak                           |                 1,778,720,768 bytes |
| API cgroup OOM kills                      |                                   1 |
| SQL provider current / peak cgroup memory | 5,140,017,152 / 5,272,653,824 bytes |

The API's 4 GiB container limit was not reached. The API worker was selected by
the Docker VM's aggregate OOM pressure while the four DuckDB workers retained
roughly 1.1-1.3 GiB each. Per-worker `/ready` remained below its 1,536 MiB
ceiling, so the current health check does not protect aggregate service or VM
capacity.

## Shared failure pattern audit

| Path                       | Current unbounded or repeated work                                                                                                         | Consequence                                                                       |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| Import pre-check           | `list_samples(count=1)` does not put `count` in the Flight ticket; the client receives all 300k rows                                       | A one-row existence check materializes the full inspection                        |
| Import transfer            | Flight batches are appended to a Python list, combined into one `pa.Table`, converted to Polars, then batched again                        | Transfer is not end-to-end streaming and duplicates the full table                |
| Import conversion          | Rows pass through dicts, Pydantic objects, image dicts, and `pa.Table.from_pylist()`                                                       | Python CPU and allocation dominate Parquet write time                             |
| Sparse manifest            | 300k Pydantic `SampleLocator` objects are embedded in `manifest.json` and retained by an unbounded manifest cache                          | Finalization and steady RSS are O(rows)                                           |
| Sparse pagination          | A small page builds and sorts `list(manifest.sample_index.keys())`                                                                         | A 100-row request still allocates over all 300k identities                        |
| Dataset overlay            | Every annotation/prediction revision collects the full sparse dataset and writes a 300k-row overlay                                        | A one-row annotation invalidates and rebuilds full-dataset state                  |
| Annotation reads           | Stats, recent items, and ID-filtered reads load every sidecar and convert every row to Python records                                      | Latency and RSS grow with annotation history; tiny files accumulate               |
| Prediction materialization | The full LazyFrame is collected; missing IDs and every image byte are kept in dictionaries before Parquet is written                       | 300k prediction is expected to exhaust memory before inference                    |
| Prediction runtime         | `_prediction_samples()` converts the re-iterable Parquet dataset into one Python list                                                      | Materialized images are duplicated in memory                                      |
| Prediction persistence     | All new shards and the previous accumulated Parquet are read, concatenated, deduplicated, and written through one in-memory buffer         | Completion cost and peak memory are O(all predictions)                            |
| Prediction progress        | Status and info logging can flush every 50 rows                                                                                            | A 300k job can create about 6,000 DB updates and log messages                     |
| Training                   | Per-class selection is capped, but materialization and trainer input still use full collects/lists and have no explicit total-byte ceiling | Many active classes or large images can still exceed worker memory                |
| DuckDB query workers       | A long-lived connection can retain allocator/buffer memory after query cleanup; four 1 GiB workers consume most of the local VM            | Unrelated API workers can be OOM-killed even when each provider worker is “ready” |

## Decisions to implement

### 1. Add a bounded Arrow batch boundary

Extend the upstream port with two explicit operations:

- `get_sample_count(inspection_time, wafer_key) -> int`, using inspection
  metadata where authoritative and a count query otherwise;
- `stream_sample_batches(..., offset, count, batch_rows) -> AsyncIterator[RecordBatch]`.

Flight tickets carry projection, offset, count, and batch size. The API client
must yield each received batch and close the reader on cancellation. It must not
append batches to a list or return a full `pa.Table` for import.

The old LazyFrame method remains only for bounded interactive callers while
they migrate. Import and cache construction are forbidden from using it.

### 2. Write sparse data columnarly

Transform each Arrow batch with Arrow/Polars expressions and give the resulting
RecordBatch/Table directly to a streaming sparse writer. New SC source schema
v3 shards preserve the complete upstream Arrow columns plus required platform
identity columns; they do not repeat three deterministic patch-image structs
per defect. The first batch establishes the concrete schema recorded in the
manifest, and later batches must match it. Patch and review images are resolved
on demand. Existing source schema v2 shards retain their explicit embedded
`images`-column read path.

The writer persists the SC source `schema_version` in both the dataset manifest
and Parquet metadata. This source version is independent of the manifest layout
`manifest_version`; both currently use the string `v3`, but describe different
contracts.

Remove per-row coroutine calls and forced full `gc.collect()` calls after the
bounded ownership model is verified. Record transfer, transform, Parquet,
checksum, upload, manifest, and cleanup time separately.

### 3. Replace the inline sample index

Introduce sparse manifest layout v3:

- `manifest.json` contains dataset, schema, shard, row-count, checksum, and
  index-object metadata only, so its size is O(shards);
- a compact Parquet index stores `sample_id`, `shard_index`, and `row_index`,
  sorted by `sample_id` with row-group statistics;
- page reads navigate shard row ranges directly when no identity filter is
  present;
- ID lookup and bulk validation query the index sidecar with predicate
  pushdown and only materialize requested locators.

Readers support explicit v2 and v3 manifest layouts during migration; all new
writes use manifest layout v3. Independently, SC rows support source schema v2
for reads and v3 for current writes. These are schema compatibility paths, not
failure fallbacks. The manifest cache becomes byte-bounded and exposes hits,
evictions, and retained bytes.

### 4. Split mutable overlays by kind

Do not construct a full 300k-row dataset overlay. Persist and cache independent
annotation and prediction state:

- annotation deltas contain only changed sample IDs;
- prediction job shards remain immutable;
- compact “current state” objects are built with DuckDB/Polars streaming COPY,
  not Python lists;
- annotation and prediction cache keys use their own content revision/fingerprint
  so an annotation does not rebuild prediction state and vice versa.

The provider's `samples` view uses the immutable base plus `LEFT JOIN` against
the current annotation and prediction overlays. `final_class` is computed in
the view. The public monotonic dataset revision and SSE event shape remain
unchanged.

Annotation compaction runs after explicit file-count/byte thresholds. Reads for
stats, recent entries, and selected IDs use projection, predicate, aggregate,
and limit pushdown. They do not call `load_all()`.

### 5. Stream prediction end to end

Change the SC materializer to iterate bounded LazyFrame/Parquet batches. For
each batch it resolves only that batch's images, writes the materialized
Parquet batch, releases the image map, and then advances. The image fetch stream
has explicit concurrency and byte limits.

Change `_prediction_samples()` to an iterator. The existing ML kernels already
accept `Iterable`, so model loading occurs once and inference consumes bounded
batches without first building a 300k-element list.

Prediction output is appended to immutable job shards. Replace the in-memory
“existing + all new frames + unique + BytesIO” merge with one of these explicit
storage operations:

1. atomically promote a complete full-dataset job as the current snapshot; or
2. append a partial-job delta and compact snapshots with DuckDB streaming COPY.

The selection is determined from job coverage, not dataset type. Progress DB
writes and logs use explicit row and time intervals from configuration.

### 6. Bound training by bytes as well as rows

Keep the 1,000-per-class rule, add an explicit total-row and materialized-byte
budget, and stream materialization batches. Training kernels may still receive
a list when required, but only after the configured budget is verified. A job
that exceeds the budget fails with a capacity error before fetching all images.

### 7. Make DuckDB worker capacity enforceable

Benchmark supported DuckDB 1.5.5 allocator controls in this order:

- enable allocator background threads;
- disable insertion-order preservation where SQL has no `ORDER BY` dependency;
- lower allocator flush thresholds;
- unregister Arrow datasets and trim/recycle the single connection after a
  completed or cancelled stream when RSS remains above a soft watermark.

Connection recycle never creates more than one active DuckDB connection per
worker. If allocator tuning cannot return RSS, recycle is required rather than
leaving a permanently unready worker.

Worker count and per-worker DuckDB memory become independently explicit for
development, four-worker acceptance, Compose production, and Kubernetes. The
four-worker acceptance profile remains mandatory, but an everyday dev profile
must fit the whole stack inside its declared Docker VM budget. Capacity
validation fails startup when:

```text
workers * (duckdb_memory + measured_python_overhead) + service_headroom
    > container_memory_limit
```

## Implementation sequence

### Phase 0 — reproducible guardrails

1. Extend the benchmark to sample per-container cgroup current/peak memory,
   OOM counters, PIDs, cache bytes, response bytes, spill, and API health
   latency throughout the run.
2. Add deterministic 300k and 1M fixtures plus cancellation and client-disconnect
   cases.
3. Record clean-process cold/warm baselines; do not reuse a provider or API
   process with unknown retained memory.

### Phase 1 — import streaming and schema v3

1. Add count and batch-stream upstream contracts and Flight tests.
2. Remove the full-table pre-check and double transfer.
3. Add the columnar sparse writer and v3 index sidecar.
4. Migrate page and ID lookup to shard ranges/index pushdown.
5. Verify v2 read compatibility, v3 writes, cancellation cleanup, and no orphan
   partial manifests.

### Phase 2 — annotation and provider overlays

1. Replace full-manifest ID validation with the v3 index query.
2. Add annotation delta metadata, current-state compaction, and pushed-down
   stats/recent/ID reads.
3. Split provider annotation/prediction objects and change the SQL view to left
   joins.
4. Prove a one-row annotation leaves the inspection base and prediction object
   as cache hits.

### Phase 3 — prediction and training runtime

1. Stream image materialization and iterator-based prediction input.
2. Replace accumulated prediction merging with snapshot promotion/delta
   compaction.
3. Tune progress persistence/logging and add training total-byte admission.
4. Run combined Train & Predict against 300k without an API or provider restart.

### Phase 4 — worker memory and production-shaped acceptance

1. Apply DuckDB allocator/connection lifecycle changes and explicit capacity
   validation.
2. Run single-worker, four-worker Compose, and one-worker-per-Pod Kubernetes
   profiles.
3. Repeat 100 page refresh/SSE reconnect cycles, annotation changes, worker
   restarts, cache cleanup, and concurrent queries.
4. Only after measured approval, revise production worker/memory values and
   close the performance issues.

## Acceptance gates

- API `/health` and `/ready` p95 stay below 500 ms during 300k and 1M import.
- No cgroup `oom_kill` increment occurs in API, provider, or runtime workers.
- Import peak RSS is bounded by configured batches; increasing 300k to 1M rows
  does not increase peak RSS by more than 20%.
- Manifest JSON is O(shards), and a 100-row page or 100-ID annotation does not
  load a 300k locator map.
- A one-row annotation does not rebuild or rewrite a 300k-row provider overlay.
- Prediction peak memory is bounded by model memory plus configured image and
  output batches, not total dataset rows.
- Prediction completion never concatenates all historical/current prediction
  rows in Python memory.
- After 100 refresh/reconnect/query cycles, every provider worker returns below
  its soft RSS watermark; RSS and DuckDB temp usage show no monotonic trend.
- Four-worker responses use multiple PIDs, share the same revision, and meet the
  reviewed cold/warm p50/p95 without exceeding the declared service capacity.

## Verification commands

Run narrow checks after each phase, then the full gates:

```text
make lint
uv run --directory apps/api --extra dev python -m pytest app/modules/sc/tests -q
uv run --directory apps/api --extra dev python -m pytest app/modules/prediction/tests -q
ruff check apps/api
uv run --directory apps/api pyright .
make test
make test-web
make build-web
make test-e2e
make e2e-live
```

The live suite must run from a clean dev database/object store/cache namespace
and must report the benchmark measurements in addition to pass/fail status.

## 2026-08-02 acceptance follow-up

The local 300k import, annotation, filtered training/prediction, DuckDB overlay,
four-worker query, and 100-cycle reconnect checks passed. The four-worker
numbers are recorded in
[`sc-data-provider-benchmark.md`](sc-data-provider-benchmark.md); import timing
is recorded in
[`sc-import-performance-issues.md`](sc-import-performance-issues.md).

Two findings remain open and must not be hidden by the bounded functional E2E:

- **SC-PREDICTION-PERF-001:** the CPU-only local compatibility predictor
  processed roughly 38-52 rows/second in an unfiltered 300k run (10,513 rows in
  about 4.5 minutes in one observation), projecting to roughly two hours for a
  complete job. The filtered E2E proves contract and overlay correctness, not
  full-dataset throughput. Profile image decode, model inference, batch size,
  and prediction persistence before setting the production acceptance gate.
- **SC-PREDICTION-LIFECYCLE-001:** cancelling the Prefect flow during that
  performance probe left the corresponding prediction job row in `running`.
  Define cancellation reconciliation and add a test requiring the persisted
  job to reach a terminal cancelled/failed state.
