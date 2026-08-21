# Image resolution service

`image-parser` is the only runtime that downloads, caches, and parses SC image
source artifacts. Browser Display, Prediction, Training, and image-bearing
Export use one deployment and one equipment-entry model; API and Prefect worker
images do not embed a second parser binary.

## Public surfaces

- Authenticated HTTP `/sc/images/...` and `/sc/sprites/...` serve browser
  display. The web gateway forwards `/api/v1/sc/images/...` and
  `/api/v1/sc/sprites/...` directly here. A browser may provide the API access
  token through the `token` query parameter; normal clients use a Bearer header.
  Sprite requests may opt into display-only grayscale mapping with the complete
  query tuple `gray_lut`, `z_min`, and `z_max`. The renderer accepts 8-bit and
  16-bit grayscale content, including opaque RGB containers whose channels are
  exactly equal, applies normalized `[0, 1]` z-limits before resize, and
  resolves a fixed 256-entry grayscale, inverted, Viridis, Inferno, or Turbo
  LUT. Mapping applies only to Patch cells; Review cells remain in their source
  colors. Raw `/sc/images/...` responses are never transformed.
- gRPC `StreamPredictionImages`, `StreamTrainingImages`, and
  `StreamExportImages` are separate bidirectional streams with independent
  traffic metrics and resource lanes. They share request/result messages but
  cannot be substituted for one another by the caller.
- HTTP `/health`, `/metrics`, and gRPC `Health` are operational surfaces. There
  is no generic format-selection RPC, subprocess frame protocol, or cache-warm
  compatibility endpoint.

One stream can open several explicit `(inspection_time, wafer_key)` contexts.
Opening resolves the Inspection and its `eqp_id` once, returns the exact
equipment ID, and advertises the batch, response-byte, and active-context
limits. One monotonically increasing sequence identifies one sample and all
requested roles. The service may work concurrently but sends results in
sequence order. Clients reopen contexts and resend from the first unacknowledged
sequence after a transport failure.

The gRPC stream surfaces return raw compressed image bytes and content type.
Decode, resize, channel stacking, tensor construction, model batching, and
inference remain algorithm responsibilities. The HTTP sprite surface is the
display-only exception: it already decodes and resizes cells, and may apply the
explicit grayscale LUT described above.

## Equipment entries

An exact code-owned registry maps explicit `eqp_id` values to an
`Equipment.Factory`. Unknown, empty, and duplicate equipment IDs fail; requests
cannot select a parser, source root, downloader, file format, or staging policy.

The current `sc.legacy-range-zip.v1` entry owns these fixed rules:

- patch archives contain at most 500 consecutive defects;
- members use six-digit defect IDs plus `PatchReference`, `PatchDefective`, or
  `PatchDifference`;
- up to eight selected archives may be opened concurrently;
- missing members are item errors, while inspection/catalog/archive failures
  close only that context with a typed context error.

Another equipment layout belongs in another registered entry. Do not restore a
generic source-format switch or infer behavior from extensions.

`sc.sqlite-image-rows.v1` is the included second entry example. It reads one
service-cached SQLite artifact through the pinned pure-Go
`modernc.org/sqlite v1.55.0` driver. Its fixed table contract is:

```sql
CREATE TABLE images (
  sample_id TEXT NOT NULL,
  role TEXT NOT NULL,
  image_bytes BLOB NOT NULL,
  content_type TEXT NOT NULL,
  PRIMARY KEY (sample_id, role)
);
```

A concrete provider must implement inspection-to-artifact discovery and
download, then register the factory for explicit equipment IDs. The entry opens
the cached database read-only, batches sample/role lookup, preserves request
order, and reports missing rows as item errors. No Parquet equipment entry is
provided.

## Artifact cache

Every equipment entry separates two interfaces:

1. the downloader describes a source as
   `ArtifactRef(entry_id, source_identity, revision, kind)` and streams it into
   the supplied staging destination;
2. the parser reads the locally published file or directory and returns image
   bytes.

The service owns one Artifact Cache Manager contract. Display, Prediction,
Training, and Export use separate subdirectories and independent TTL, capacity,
concurrency, and metrics. `Acquire` returns an Artifact lease rather than an
unowned path. Readers hold a shared filesystem lock until every file, directory,
database, or index retaining those handles is closed; Janitor eviction requires
the same entry's exclusive lock and therefore skips active readers. A
miss acquires process singleflight and the exclusive lock before downloading,
rechecks the final target, writes to a sibling temporary location, rejects
symlinks, fsyncs, and atomically renames. A directory is measured recursively
and evicted as one indivisible artifact. Coordination and staging files are
never counted or deleted as cache objects.

Source revision precedence is S3 VersionId, then ETag, then reliable source
LastModified plus size. Local cache mtime is only LRU/TTL metadata. Directory
entries require a provider generation or manifest revision.

Base cache variables are `CACHE_DIR`, `CACHE_TTL`,
`CACHE_CLEANUP_INTERVAL`, and `CACHE_MAX_BYTES`. Each semantic namespace can
override `DISPLAY_CACHE_*`, `PREDICTION_CACHE_*`, `TRAINING_CACHE_*`, or
`EXPORT_CACHE_*` (`TTL`, `CLEANUP_INTERVAL`, and `MAX_BYTES`).

## Required connections

The service fails startup when a required connection is absent:

| Variable                                                      | Purpose                                                         |
| ------------------------------------------------------------- | --------------------------------------------------------------- |
| `SC_UPSTREAM_ADDR`                                            | Inspection, equipment, archive catalog, and review locator gRPC |
| `SC_PATCH_S3_ENDPOINT`, `REGION`, `ACCESS_KEY`, `SECRET_KEY`  | Patch archive source                                            |
| `SC_REVIEW_S3_ENDPOINT`, `REGION`, `ACCESS_KEY`, `SECRET_KEY` | Review image source                                             |
| `JWT_SECRET_KEY`                                              | Shared HS256 key for browser HTTP image authentication          |

The S3 fields may explicitly use the corresponding `MINIO_*` environment
values. There are no mock credentials or localhost defaults. `GRPC_LISTEN`
accepts `tcp://<address>` or `unix:///absolute/socket/path`; a Unix listener
removes only a stale socket and refuses to replace a regular file.

## Verification

`make benchmark-image-stream-receipt` creates a deterministic 300,000-sample,
two-image range-ZIP fixture, warms the Artifact Cache, then measures production
ZIP parsing through the public Prediction stream to the generated Python
client. The gate is 3,000 samples/second. Fixture generation, cold download,
and decode/fake-predictor throughput are reported separately.
