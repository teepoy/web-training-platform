# Image resolution service

`image-parser` is the only runtime that downloads, caches, and parses SC image
source artifacts. Browser Display, Prediction, Training, and image-bearing
Export use one deployment and one equipment-entry model; API and Prefect worker
images do not embed a second parser binary.

## Public surfaces

- Authenticated HTTP `/sc/images/...`, `/sc/sprites/...`, and
  `/sc/inspections/{inspection_time}/{wafer_key}/image-profile` serve browser
  display. The web gateway forwards their `/api/v1/sc/...` aliases directly
  here. A browser may provide the API access
  token through the `token` query parameter; normal clients use a Bearer header.
  Sprite requests may opt into display-only grayscale mapping with independent
  complete query tuples prefixed `defective_reference_` and `difference_`.
  Each tuple selects `gray_mode=global|adaptive`. Global mode applies its
  normalized z-window across the Inspection profile. Adaptive mode performs a
  per-defect min-max normalization: Defective and all Reference instances share
  one observed range, while each Difference instance uses its own range.
  Constant images map to the LUT minimum. The renderer accepts 8-bit,
  12-bit, and 16-bit grayscale content, including opaque RGB containers whose channels are
  exactly equal, applies bit-depth-relative normalized `[0, 1]` z-limits before resize, and
  resolves a fixed 256-entry grayscale, inverted, Viridis, Inferno, or Turbo
  LUT. Mapping applies only to Patch cells; Review cells remain in their source
  colors. Patch sprite enlargement uses nearest-neighbor pixel replication so
  integer scale factors produce solid source-pixel blocks without interpolation;
  Review sprite resizing retains smooth interpolation. Raw `/sc/images/...`
  responses are never transformed. A sprite request batch-resolves all cells,
  decodes each compressed image once, renders directly into the final canvas,
  and encodes only the final PNG.
  The image-profile response lists every Patch instance (including multiple
  Reference, Difference, and Mask IDs) and its native bit depth and observed
  inspection-wide min/max. Artifact revisions key a bounded metadata LRU, so
  repeated Settings reads do not rescan cached artifacts.
- Authenticated POST `/sc/gallery-downloads` accepts only the caller's explicit
  Gallery selection. It prepares a temporary ZIP on the Export cache/traffic
  lane and streams the completed file as an attachment. Original PNG/JPEG
  bytes and dimensions are preserved by default; an explicit option applies
  the current grouped Patch mappings without resizing and writes mapped PNGs.
  Review images are never mapped.
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
limits plus the bounded number of request batches that a client may prefill.
Prediction currently advertises two in-flight batches; Training and Export
advertise one. The receive queue is bounded by that value, while parsing and
responses remain request- and sequence-ordered. One monotonically increasing
sequence identifies one sample and all requested roles. Clients reopen
contexts and resend from the first unacknowledged sequence after a transport
failure.

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

`sc.sqlite-inspection-images.v1` is the fixed Snappy inspection example. Its
checked-in fixture is
`internal/equipment/sqliteinspectionimages/testdata/multi-reference-difference-12bit.sqlite`
and uses:

```sql
CREATE TABLE inspection_images (
  id INTEGER PRIMARY KEY,
  defect_id INTEGER NOT NULL,
  image_type TEXT NOT NULL,
  image_id INTEGER,
  image_value BLOB NOT NULL
);
```

`T/R/D/M` map to Defective/Reference/Difference/Mask. `image_id` distinguishes
multiple instances. `image_value` is a `2E9C` prefix followed by one raw Snappy
block; the decoded payload is either `Gray8[32x32]` or big-endian 12-bit values
stored as `uint16[32x32]` (values above 4095 fail explicitly). The entry emits PNG bytes, keeps one read-only SQLite
connection per immutable artifact, and caches inspection profiles in a bounded
revision-keyed in-memory LRU.

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

Source adapters must return a stable identity and revision. An object-store
adapter can use VersionId, then ETag, then reliable source LastModified plus
size. Local cache mtime is only LRU/TTL metadata. Directory entries require a
provider generation or manifest revision.

Base cache variables are `CACHE_DIR`, `CACHE_TTL`,
`CACHE_CLEANUP_INTERVAL`, and `CACHE_MAX_BYTES`. Each semantic namespace can
override `DISPLAY_CACHE_*`, `PREDICTION_CACHE_*`, `TRAINING_CACHE_*`, or
`EXPORT_CACHE_*` (`TTL`, `CLEANUP_INTERVAL`, and `MAX_BYTES`).

## Required connections

The service fails startup when a required connection is absent:

| Variable           | Purpose                                                         |
| ------------------ | --------------------------------------------------------------- |
| `SC_UPSTREAM_ADDR` | Inspection, equipment, archive catalog, and review locator gRPC |
| `JWT_SECRET_KEY`   | Shared HS256 key for browser HTTP image authentication          |

Patch archives and Review images are production-owned `ArchiveSource` and
`ReviewImageSource` ports. The default production build does not link a source
implementation and fails explicitly until the deployment supplies real
adapters. Development implementations remain outside the production package
and runtime image.

There are no mock credentials or localhost defaults. `GRPC_LISTEN`
accepts `tcp://<address>` or `unix:///absolute/socket/path`; a Unix listener
removes only a stale socket and refuses to replace a regular file.

## Verification

`make benchmark-image-stream-receipt` creates a deterministic 300,000-sample,
two-image range-ZIP fixture, warms the Artifact Cache, then measures production
ZIP parsing through the public Prediction stream to the generated Python
client. The client fills the advertised request window and refills it after
each acknowledgement. The gate is 3,000 samples/second. Fixture generation,
cold download, and decode/fake-predictor throughput are reported separately.
