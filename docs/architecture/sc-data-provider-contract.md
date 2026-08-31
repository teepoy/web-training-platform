# SC Data Provider Contract

## Status

Implemented. Preview and Reclassify use the provider-neutral
`ScWorkbenchDataSource`; Perspective is not a runtime or fallback dependency.

## Process boundary and protocol

The normal API and SC data provider remain separate processes and containers.

```text
browser -- HTTP SQL / Arrow IPC --> sc-data-provider:8001
browser <-- SSE invalidation ----- sc-data-provider:8001
browser -- control-plane HTTP ----> api:8000
```

Compose runs:

```text
uvicorn app.sc_data_provider_main:app --host 0.0.0.0 --port 8001 --workers 4
```

Kubernetes runs one Uvicorn worker per Pod and uses four Deployment replicas.
Nginx proxies `/api/v1/sc/data/` to the single `sc-data-provider:8001`
upstream. `curl` is only a debugging client; the application protocol is HTTP +
SQL + Arrow IPC, with SSE for invalidation.

## Browser interface

`ScWorkbenchDataSource` provides:

- `loadMap`, `loadRows`, `loadGallery`, `loadAggregates`, and
  `loadDistinctValues` for read projections;
- `resolveSelection` for ID, all-row, rectangle, polygon, legend, and random
  selection constraints;
- `loadHighlights` for ID-projected map highlights;
- `subscribeInvalidations` and `close` for lifecycle management.

Map and table selections are local workbench state. They become parameterized
query constraints only where consumed. There are no `map_in_selection` or
`table_in_selection` columns, update ports, or server-side UI table mutations.
Table select-all is a compact `all` query constraint. It never materializes the
matching defect IDs in the browser; optional deselections are carried as a
small exclusion list.

`InspectionQuad` owns the Global Filter state because its map, table, gallery,
aggregate, and selection queries consume that state together. Preview and
Reclassify parents do not provide a filter prop or update event. A parent
workflow such as Train & Predict may request a cloned filter snapshot through
the component handle, but it must not mutate or synchronize the live filter.
The exact ownership, transition, and consumer matrix is defined in
[`sc-inspection-workbench-filter-contract.md`](sc-inspection-workbench-filter-contract.md).

## HTTP query contract

Three authenticated scopes are available:

```text
POST /api/v1/sc/data/inspections/{inspection_time}/{wafer_key}/query
POST /api/v1/sc/data/datasets/{dataset_id}/query
POST /api/v1/sc/data/collections/{collection_id}/revisions/{revision_id}/query
```

The strict request schema is:

```json
{
  "description": "sc-workbench.table.rows",
  "sql": "SELECT defect_id FROM samples WHERE rough_bin = ANY(?) ORDER BY defect_id LIMIT ?",
  "parameters": [[1, 2, 3], 200]
}
```

`description` and `parameters` are required. `description` is a bounded,
machine-readable caller/usage label such as `sc-workbench.map`,
`sc-workbench.gallery.patch`, or `sc-workbench.selection.rectangle`; the data
provider echoes it in `X-SC-Query-Description` and includes it in its info log.
Each parameter is a JSON scalar or a non-empty homogeneous array of booleans,
numbers, or strings. SQL identifiers are selected from a frontend allowlist;
user values never enter SQL text.

Only one `SELECT` or `WITH ... SELECT` statement is accepted. It may reference
only the scope-local `samples` and `review_images` views or its own CTEs. The AST
policy rejects catalog/schema-qualified names, table functions, unapproved
functions, DDL, DML, `ATTACH`, `COPY`, `PRAGMA`, transactions, extension loading,
and file/network scans. The DuckDB connection independently disables external
access, Python replacement scans, extension auto-install, and extension
autoload.

Representative queries:

```sql
-- Ordered/paged table
SELECT defect_id, rough_bin, class_number, COUNT(*) OVER () AS __total
FROM samples
WHERE class_number = ?
ORDER BY defect_id
LIMIT ? OFFSET ?

-- Legend aggregate
SELECT rough_bin AS group_key, COUNT(*) AS group_count
FROM samples
WHERE wafer_x >= ? AND wafer_x <= ?
GROUP BY rough_bin
ORDER BY rough_bin

-- Compact rectangle selection
SELECT defect_id
FROM samples
WHERE wafer_x >= ? AND wafer_x <= ? AND wafer_y >= ? AND wafer_y <= ?
ORDER BY defect_id

-- Explicit ID and all-result constraint resolution use the same projection
SELECT defect_id FROM samples WHERE defect_id = ANY(?) ORDER BY defect_id
SELECT defect_id FROM samples ORDER BY defect_id
```

The remote sample-table header checkbox represents the whole filtered result
set with an `all` constraint. Gallery queries reuse the current filters and add
no ID predicate for that state. Deselecting individual rows adds only those IDs
to an exclusion predicate; no whole-result-set action expands IDs in the
browser.

The response body is `application/vnd.apache.arrow.stream`. Headers include:

- `X-SC-Data-Revision` — revision used by the materialized scope;
- `X-SC-Query-Description` — the request's validated caller/usage label;
- `X-SC-Worker-PID` — serving Uvicorn worker;
- `X-SC-Cache` — `hit` or `miss` for normalized objects;
- `X-SC-Spill-Bytes` — current worker spill-directory bytes when headers are
  prepared;
- `Server-Timing` — materialization and DuckDB time-to-first-stream-chunk.

The SQL timeout is 30 seconds and the maximum Arrow response is 256 MiB.
Execution uses one DuckDB connection and a one-thread queue per worker. Arrow
batches cross into the async response through an eight-item bounded queue, so a
slow or disconnected browser cannot create an unbounded response backlog.
Timeout and disconnect cleanup always releases that worker's query lock, even
when `interrupt()` races with a connection recycle. A failed recycle leaves no
closed connection registered as usable; the next request creates a fresh
connection instead of repeatedly returning `Connection already closed`.

## Revisions and server-side updates

Dataset annotation and prediction writers persist first. Their Redis event
publisher then atomically increments
`sc-data-provider:revision:dataset:{dataset_id}`, adds the new revision to the
event payload, and publishes the invalidation in one Lua operation.
When revision-aware Redis publishing is unavailable, the write path reports an
explicit error instead of silently serving a permanently stale cached overlay.

Clients subscribe at:

```text
GET /api/v1/sc/data/inspections/{inspection_time}/{wafer_key}/events
GET /api/v1/sc/data/datasets/{dataset_id}/events
GET /api/v1/sc/data/collections/{collection_id}/revisions/{revision_id}/events
```

An SSE invalidation contains `scope`, a monotonic `revision`, and
`changed_kinds`. The browser refetches affected projections and discards an HTTP
response whose revision is below its latest observed revision. This removes
worker affinity: an update and the following query may land on different
workers.

An individual SSE response is capped at 60 seconds and advertises the cap in
`X-SC-SSE-Max-Connection-Seconds`. Native `EventSource` reconnects while a
workbench still has invalidation listeners, so rotation preserves live updates
without keeping one server request open indefinitely. The initial revision
baseline does not trigger a redundant refetch when it equals the revision the
client already knows. Removing the last listener closes the browser
`EventSource` immediately; the provider always unsubscribes and closes its
Redis Pub/Sub handle when the response expires or the client disconnects.

## Object cache and cleanup

Final SQL results are never cached. The cache contains only normalized,
rebuildable Parquet objects:

- inspection base samples keyed by the required Inspection `change_token`;
- inspection review-image rows keyed by the same `change_token`;
- a dataset annotation/prediction overlay at its dataset revision.

Dataset and Collection bases are built by semi-joining their persisted identity
membership with the latest inspection rows. Stored source extras from v2/v3
shards are ignored. Each source read sends bounded defect-ID chunks and an exact
projection over Arrow Flight; the SC upstream adapter applies the inspection PK
and defect-ID predicate before returning rows rather than streaming the full
inspection for an API-side filter. The API resolver reads membership through
streaming Polars batches, joins only one bounded source chunk at a time, and
writes resolved chunks to a context-owned temporary Parquet file. A disk-backed
identity index detects duplicates across chunks without retaining all IDs in
memory. The temporary file is deleted when the consumer closes the resolver
context and is never a Dataset source of truth. Inspection freshness and
review-image metadata reads bypass tokenless metadata caches, and membership
sample reads do not use the full-inspection cache. Dataset `samples` is then a
query-time join of that current source projection and the platform overlay. A
cache object ID is
the SHA-256 of its logical key, source freshness, and platform revision. Redis
stores object metadata and access order; the file itself stays in the configured
cache directory.

Production deployments provide the SC upstream database adapter through the
configured adapter factory. That external adapter must implement the bounded
membership-read operation and apply both the canonical inspection-PK predicate
and defect-ID predicate in its source database before yielding projected Arrow
batches; filtering a full inspection inside `sc-upstream` is not compatible with
this contract. Service startup validates that method is present. Inspection
records must also expose a positive opaque `change_token`; missing or non-positive
tokens fail with a gRPC precondition error.

Every visible Sample-table column has one authority:

| Column category                                                              | Authority                                         |
| ---------------------------------------------------------------------------- | ------------------------------------------------- |
| `sample_id`, `defect_id`, Dataset/Collection membership                      | Persistent identity shard and Collection revision |
| Inspection coordinates, bins, class/source metadata, mutable upstream fields | Latest SC upstream projection                     |
| Annotation labels and annotation identity                                    | Platform annotation overlay                       |
| Prediction labels, confidence, and prediction identity                       | Platform prediction overlay                       |
| `row_key`, map/reticle values, display counts, and other view-only values    | Disposable query derivation                       |

Neither the browser nor the generic storage aggregate chooses between these
authorities. A missing upstream row or unavailable upstream fails a
source-dependent query before overlays are exposed.

### Build and publication

1. A reader validates Redis metadata, exact path, file size, and Parquet
   metadata. A valid object is a cache hit.
2. A miss tries an expiring Redis build lock. One worker builds; competing
   workers poll for the published object for at most 30 seconds.
3. The builder writes `tmp/{uuid}.parquet` and atomically renames it to
   `objects/{sha256}.parquet`.
4. Only after rename does it publish Redis metadata and LRU access time. A crash
   before rename leaves a stale temp file, never a visible partial object.

### Leases

Before opening Parquet objects, a query creates per-object Redis lease keys with
a 60-second TTL and renews them every 20 seconds. It releases leases after the
Arrow stream completes, errors, is cancelled, or the browser disconnects. A
crashed worker stops renewing, so leaked leases become collectible without
manual repair.

### Cleanup order

One Redis-elected cleanup leader runs every 60 seconds:

1. remove temp writes older than 300 seconds;
2. discard malformed or mismatched Redis metadata;
3. remove old orphan files that have no valid metadata;
4. remove old-revision or idle objects only when they have no active lease;
5. if disk use exceeds 10 GiB, evict unleased objects from least recently used
   until usage is at or below 8 GiB.

The idle TTL is 3600 seconds. Old revisions can be removed immediately after
their last lease ends; current revisions remain until idle or watermarks require
eviction. A transient Redis/filesystem cleanup error is logged and retried on
the next interval. It never changes query implementation or activates a
fallback.

Compose workers share `/mnt/sc-data-provider-cache` or the named development
volume and one Redis cache namespace. Kubernetes uses an `emptyDir` per Pod and
sets the Redis object-cache namespace from the Pod name; the distinct revision
namespace remains global across Pods. This prevents one Pod from accepting
metadata for files that exist only in another Pod.

## Explicit capacity configuration

| Setting                        |          Value |
| ------------------------------ | -------------: |
| Compose Uvicorn workers        |              4 |
| DuckDB memory per worker       |          1 GiB |
| DuckDB threads per worker      |              1 |
| DuckDB spill limit per worker  |          2 GiB |
| Worker readiness RSS ceiling   |       1536 MiB |
| Shared object-cache high / low | 10 GiB / 8 GiB |
| Object idle TTL                |         3600 s |
| Cleanup / stale-write interval |   60 s / 300 s |
| Lease TTL / heartbeat          |    60 s / 20 s |
| SQL timeout / maximum response | 30 s / 256 MiB |
| SSE response cap / heartbeat   |    60 s / 15 s |

Development uses tracked `logging.level: INFO`. Every `/health` and `/ready`
call logs worker RSS at info level and returns RSS, worker PID, and current
DuckDB temp bytes.

## Verification

Run focused contract checks and the two reproducible performance tools:

```text
uv run --directory apps/api --extra dev python -m pytest app/modules/sc/tests -q
uv run --directory apps/api --extra dev python scripts/benchmark_sc_duckdb_engine.py
uv run --directory apps/api --extra dev python scripts/benchmark_sc_data_provider.py --help
```

The HTTP benchmark records cold/warm p50/p95, Arrow bytes, revision, cache
status, worker PIDs, `Server-Timing`, RSS, spill bytes, and 100 SSE reconnect +
query cycles. See `sc-data-provider-benchmark.md` for the checked-in migration
baseline and the commands required for a deployment-specific four-worker run.
