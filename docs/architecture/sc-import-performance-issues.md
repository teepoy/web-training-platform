# SC 300k Import Performance Issues

Status: Bounded-execution remediation implemented; live acceptance pending
Recorded: 2026-08-01
Scope: SC inspection to `file_shard_sparse` dataset import

This document records the performance and isolation issues observed during the
300,000-defect live import. It is a follow-up backlog, not evidence that the
current import path is production-ready.

The implementation sequence and the audit of the related annotation,
prediction, training, and SQL data-provider paths are defined in
[`sc-pipeline-performance-plan.md`](sc-pipeline-performance-plan.md).

## Remediation status

| Issue              | Code status                                                                                                                                                                                                     | Remaining verification                                                                        |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| SC-IMPORT-PERF-001 | Resolved: Flight count and bounded async Arrow batches are used by import and provider cache construction.                                                                                                      | Clean-process 1M RSS slope and Flight cancellation against Compose.                           |
| SC-IMPORT-PERF-002 | Resolved: SC import transforms Arrow batches columnarly and writes each batch directly to Parquet/object storage.                                                                                               | Production CPU profile and the 3x wall-time gate.                                             |
| SC-IMPORT-PERF-003 | Resolved: manifest v3 stores an external Parquet index; manifest cache is byte-bounded; natural pages avoid the full identity index.                                                                            | Live random/filter workloads at 1M rows.                                                      |
| SC-IMPORT-PERF-004 | Resolved: forced full `gc.collect()` calls were removed from the request loop.                                                                                                                                  | Health latency sampling during live import.                                                   |
| SC-IMPORT-PERF-005 | Still open by architecture decision: execution is bounded and synchronous transforms run off the event loop, but import still occupies an API worker/request. Moving it to a runtime job remains separate work. | Runtime job submission, persistent progress, retry/idempotency, and importer fault injection. |
| SC-IMPORT-PERF-006 | Implemented: phase timings, HTTP health latency, response/cache/spill/PID data, cgroup current/peak/events, deterministic 300k/1M fixtures, and disconnect recovery are available.                              | Run and record the production-shaped four-worker report.                                      |

## Reproduction and baseline

Run the live Preview -> Inspection -> Reclassify flow against the aligned local
fixture (`wafer_key=1`, inspection `2026-08-01T04:00:00+08:00`) with
`SC_IMPORT_BATCH_SIZE=25000`.

Observed dataset: `6b7c53d7-5418-437c-85e4-b142f562beca`.

| Measurement                           |   Observed value |
| ------------------------------------- | ---------------: |
| Source and target rows                |          300,000 |
| Parquet shards                        | 12 x 25,000 rows |
| Row count resolved                    |          1.440 s |
| Last shard persisted                  |        159.602 s |
| Manifest/finalization tail            |         11.512 s |
| Total import                          |        171.114 s |
| Sum of logged Parquet flush durations |          3.658 s |
| API RSS at import start               |    3,314,732 KiB |
| API RSS at completion log             |    3,806,468 KiB |
| API high-water RSS                    |    3,808,132 KiB |

The API process was already warm at the start, so the RSS values are not a
clean-process allocation profile. After the completion log, Docker reported
`OOMKilled=true`; the Uvicorn worker became a zombie and `/ready` stopped
responding until the API container was restarted. At investigation time the
Docker VM exposed 7.751 GiB and the four-worker data-provider container used
about 2.741 GiB. The conclusion that aggregate VM pressure selected the API
worker is an inference from those observations and must be confirmed in a
controlled benchmark.

The frontend's ordinary 30-second HTTP timeout was also incorrectly applied to
the completion SSE. That transport bug is fixed separately and is not included
in the 171.114-second backend duration.

## SC-IMPORT-PERF-001: Flight is not streamed end to end

`GrpcScUpstreamReader._read_list_samples_table()` appends every Flight record
batch to a Python list, builds one `pa.Table`, and converts it to one Polars
DataFrame. `ScImportService` only calls `collect_batches()` after that full
materialization, so the apparent batching does not bound API memory.

Relevant code:

- `apps/api/app/modules/sc/adapter/grpc_upstream.py`
- `apps/api/app/modules/sc/app/services/sc_import_service.py`
- `services/sc-upstream/src/sc_upstream/flight_server.py`

Follow-up:

- Add a true async/bounded batch interface to `ScUpstreamReader` for imports.
- Consume Flight batches directly without constructing a full Arrow table or
  Polars DataFrame in the API process.
- Resolve total rows from inspection metadata or a dedicated count query rather
  than requiring the imported payload to be materialized first.

Acceptance:

- Import memory remains bounded as row count grows from 300k to 1M.
- A benchmark records cold/warm transfer time, first-batch latency, peak RSS,
  and bytes received for both current and streaming implementations.
- Cancelling the import closes the Flight reader and releases batch buffers.

## SC-IMPORT-PERF-002: Per-row Python conversion dominates shard time

Each batch is converted with `DataFrame.to_dicts()`, then each row becomes a
Pydantic `PatchSample`, image dictionaries are built per row, and another row
dictionary is produced for `pa.Table.from_pylist()`. `_build_image_structs()` is
also async despite performing no I/O and is awaited 300,000 times.

The logged Parquet flushes took only 0.215-0.468 seconds each, while most 25k
batch intervals took 11-20 seconds. This makes row normalization and object
construction the primary measured CPU hotspot; a CPU profile is still required
to assign exact percentages.

Relevant code:

- `apps/api/app/modules/sc/app/services/import_rows.py`
- `apps/api/app/modules/sc/app/services/sc_import_service.py`
- `apps/api/app/modules/storage/adapter/sparse/import_operator.py`

Follow-up:

- Replace row-wise Pydantic construction with Arrow/Polars column expressions.
- Build the nested image column in columnar form.
- Pass Arrow record batches/tables to the sparse writer rather than round
  tripping through `list[dict]` and `pa.Table.from_pylist()`.
- Remove coroutine overhead from pure synchronous transformations.

Acceptance:

- Capture `py-spy` or equivalent CPU profiles for at least one 300k run.
- Report rows/second and per-phase time for conversion, Arrow construction,
  Parquet encoding, checksum, and object upload.
- Demonstrate at least a 3x reduction in pre-manifest processing time without
  changing the sparse dataset contract.

## SC-IMPORT-PERF-003: The manifest and in-process cache scale O(rows)

Every imported sample creates a Pydantic `SampleLocator` stored in the
`sample_index` dictionary. The complete 300k-entry dictionary is serialized into
`manifest.json`, then `DatasetPayloadStore.put_manifest()` retains the full
Pydantic manifest in its unbounded in-process cache. Finalization took 11.512
seconds in the baseline and keeps a large object graph alive after success.

Relevant code:

- `apps/api/app/modules/storage/domain/sparse/models.py`
- `apps/api/app/modules/storage/domain/sparse/store.py`
- `apps/api/app/modules/sc/app/services/sc_import_service.py`

Follow-up requires a storage-contract decision. Candidate directions are a
compact sidecar index (Arrow/Parquet), arithmetic locators for ordered shards,
or a paged/key-value index. The manifest cache must be size-bounded and must not
retain a 300k locator graph indefinitely.

Acceptance:

- Manifest metadata size and serialization time are sublinear in row count, or
  the row index is stored and loaded independently in bounded pages.
- Random sample lookup remains correct without loading the entire index.
- Repeated imports and reads do not cause monotonic API RSS growth.

## SC-IMPORT-PERF-004: Full GC runs in the request loop without attribution

The importer calls `gc.collect()` after every 25k shard. These stop-the-world
collections run on the API request worker, but their durations are currently
included in the following batch interval and are not logged separately.

Follow-up:

- Measure generation counts, collected objects, and elapsed time for every
  forced collection.
- Remove forced full collections if ownership fixes and bounded batches make
  them unnecessary; otherwise move cleanup outside latency-sensitive sections.

Acceptance:

- The benchmark exposes GC time as its own phase.
- No unmeasured event-loop stall exceeds the configured health/SSE heartbeat
  interval.

## SC-IMPORT-PERF-005: Heavy import execution is coupled to the API worker

`POST /api/v1/sc/import/stream` creates the direct import task inside the API
process. CPU work, Arrow buffers, the full locator index, manifest serialization,
and SSE lifecycle therefore share one worker. The observed OOM removed API
readiness and prevented the browser from receiving the final dataset ID even
though the completion log had already been emitted.

This also conflicts with the repository architecture rule that production data
execution should run behind an explicit runtime boundary instead of consuming
the API control-plane process.

Follow-up:

- Move import execution to a bounded runtime/worker job; keep API/SSE as status
  submission and observation only.
- Persist progress and terminal state independently of the client connection.
- Define cancellation, retry, idempotency, partial-object cleanup, and resume
  behavior before switching the live flow.

Acceptance:

- API `/health` and `/ready` remain responsive during and after 300k and 1M
  imports, including an importer OOM/restart fault injection.
- Client disconnect does not leave an untracked import or ambiguous dataset
  state.
- A failed import can be retried without duplicate datasets or orphan shards.

## SC-IMPORT-PERF-006: Benchmark attribution is insufficient

Current logs expose total elapsed time and final `flush_shard()` time, but do not
separate upstream transfer, row conversion, Arrow construction, Parquet
compression, checksum, object-store upload, manifest construction,
serialization, upload, cache retention, or GC.

Follow-up:

- Add structured phase timing and response/progress metrics with dataset ID,
  row count, shard index, process PID, RSS, and bytes.
- Run cold/warm 300k baselines with a clean API process and record Docker VM and
  every relevant container's memory concurrently.
- Repeat with the production Uvicorn worker configuration and verify that one
  import cannot exhaust unrelated API workers.

Acceptance:

- The benchmark report can explain at least 95% of wall-clock time by named
  phases.
- Results include p50/p95, rows/second, peak/incremental RSS, output bytes, and
  failure behavior for single and concurrent imports.
