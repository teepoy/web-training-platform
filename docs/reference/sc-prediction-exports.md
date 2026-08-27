# SC prediction exports

The Dataset detail **Export** tab exports one Dataset. A Collection's **Data**
tab lets the user select linked Dataset records and export only that selection.
Both surfaces export the current accumulated classification state in three formats. The user first
selects Annotation, Prediction, or Final Class as the exported result source:

- **Annotation** exports only non-empty, non-zero human annotations.
- **Prediction** exports only rows with a current prediction.
- **Final Class** uses a non-empty, non-zero annotation, otherwise the current prediction.

The source selector also controls the distribution shown in the UI and the class distribution used
by Review Sampling.

| Format           | Contents                                                                                                                                                                                                                                                                                                                                                                                                           |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Parquet          | Current sparse Dataset columns plus annotation, prediction label, confidence, and `final_class` resolved from the selected result source.                                                                                                                                                                                                                                                                          |
| KLARF 1.2 or 1.8 | One complete file per `(inspection_time, wafer_key)`, named `{layer_id}-{lot_id}-{wafer_id}.{partition}`. The three-digit partition starts at `.000` for each filename base. The user selects the version before export. `CLASSNUMBER` contains the selected exported class; prediction-only fields stay out of the KLARF schema. Multiple files, or any export with defect images, are returned as a ZIP package. |
| ZIP package      | One combined Parquet file, all inspection-level numbered KLARF files in the selected version, `manifest.json`, and optional defect images.                                                                                                                                                                                                                                                                         |

The export is a current-state handoff, not a frozen Dataset Revision. In Final Class mode, SC code
`0` means Unclassified and does not override a prediction.

```text
Final Class = Annotation && Annotation !== 0 ? Annotation : Prediction
```

## Review Sampling

Review Sampling is optional and has its own browser preference, separate from Classify workspace
Annotation Sampling. Its first-use default is `Maximum per Wafer = 100`. An optional recursive Extra
Filter runs first; the same 17 typed rules then execute top to bottom in the server-side DuckDB
sampling engine. Every rule receives only the preceding rule's output. KLARF, Parquet, and ZIP
therefore receive the same selected sample set, and the browser never downloads all candidate rows
to perform sampling.

When Export is opened from the Classify workspace, the page-owned Global Filter is sent as the
request's independent `sample_filter` and limits the export even when Review Sampling is disabled.
Review Sampling's Extra Filter remains separate and runs after that page filter but before the
ordered sampling rules.

## API

`POST /api/v1/sc/datasets/{dataset_id}/prediction-exports/stream` returns SSE
progress, data, and terminal events. The request selects `result_source` as `annotation`,
`prediction`, or `final_class`, and `format` as `klarf`, `parquet`, or `zip`; KLARF and ZIP requests
may select `klarf_version` as `1.2` or `1.8`. Review Sampling carries a typed ordered program, seed,
and optional recursive `extra_filter`. The optional top-level `sample_filter` applies the Classify
workspace's recursive Global Filter without enabling Review Sampling. Omitted result sources keep
Final Class behavior, and omitted versions keep the earlier `1.2` behavior for existing clients. A
Parquet request carrying a KLARF version
is rejected instead of silently ignoring it. KLARF and ZIP requests may set
`include_images`; Parquet requests carrying that option are rejected. The endpoint currently requires an
`image_sc` Dataset with `task_type=sc` using `file_shard_sparse` storage. The
frontend applies the same capability gate before showing Export; incompatible
Datasets also fail explicitly at the service boundary.

`POST /api/v1/sc/dataset-collections/{collection_id}/prediction-exports/stream`
uses the same export request plus a non-empty `member_ids` list. The service
validates the selected IDs against the Collection's current linked members,
loads Dataset metadata in one query, and exports no unselected member.

For a Collection, Parquet remains one combined table and records each row's
`source_dataset_id`. KLARF grouping is different because inspection identity
matters to that format: rows are grouped by `(inspection_time, wafer_key)`, not
by Dataset and not by target byte size. Every numbered file has its own
`FileVersion` and `EndOfFile` records and is independently parseable.
Its filename is `{layer_id}-{lot_id}-{wafer_id}.{partition}`, with unsafe
filesystem characters normalized to `_` and the partition incremented as a
zero-padded three-digit counter when the same metadata base occurs more than
once in one export.

KLARF headers are sourced from imported inspection metadata (`lot_id`,
`wafer_id`, device, layer, geometry, and inspection time). Dataset or Collection
names are not substituted for semiconductor metadata. Missing required Lot,
Wafer, inspection, geometry, or numeric Final Class values fail explicitly;
the exporter does not invent them.

The flat KLARF 1.2 document is intentionally limited to fields backed by the
imported inspection. It includes the standard flat `DefectRecordSpec` /
`DefectList` and `SummarySpec` / `SummaryList` structures. Summary counts are
computed from the rows in that numbered export file; they are not copied from
an upstream summary that could disagree after Review Sampling. The exporter
does not synthesize an inspection-station vendor, orientation, full-wafer
SampleTestPlan, class descriptions, or TIFF references when those values are
unavailable.

The KLARF 1.8 output uses a hierarchical `FileRecord` -> `LotRecord` ->
`WaferRecord` subset with typed `DefectList` and `SummaryRecord` /
`TestSummaryList` records. It is not presented as an implementation of every
optional KLARF 1.8 record. Every output is parsed again in tests using the
repository's independent KLARF reader.

## Image fields

Defect images are optional and disabled by default. When disabled, the exporter
writes `IMAGECOUNT 0` with an empty `IMAGELIST` in KLARF 1.2 and `N` for the
KLARF 1.8 `ImageList` cell. Existing sample metadata such as an upstream image
count does not justify emitting a file reference when that file is absent from
the export.

When enabled, Review Sampling runs first. The exporter then resolves exactly
one `patch_defective` image for every retained row through the semantic Export
image-parser stream in bounded 512-row batches. The Export lane has its own
cache namespace and concurrency budget. KLARF 1.2 writes `IMAGECOUNT 1`, one `IMAGELIST` pair, and the
matching `TiffFileName`; KLARF 1.8 writes one `Images` entry. Every referenced
relative name must exist under `images/` in the returned ZIP. Missing/corrupt
images and unknown content types fail the whole export without uploading a
partial artifact.

A public KLARF 1.2 example shows the non-empty case as one image plus a matching
list entry and a following `TiffFileName` record. The repository parser also
keeps a two-image fixture (`IMAGECOUNT 2` with two `IMAGELIST` entries) to lock
down this counted-list grammar. See the
[public KLARF example](https://www.artwork.com/package/wmapconvert/map_formats/KLARF/index.htm)
and the [KLARF data patent](https://patentimages.storage.googleapis.com/7c/21/a2/b5aecf76c10dcc/US6744266.pdf).

## Large-file behavior

- Export generation has no browser request deadline. The server emits a progress
  heartbeat every 15 seconds, and the production web proxy allows a 30-minute
  idle window for both generation and transfer.
- Writers use temporary files and `ArtifactStorage.put_file`; MinIO therefore
  uses its file/multipart upload path instead of materializing the artifact as
  one Python `bytes` value.
- An unsampled Parquet-only export sinks the combined LazyFrame directly to the
  temporary file with Polars' streaming engine. KLARF, ZIP, and server-side
  sampled exports currently require an in-process result frame before writing.
- ZIP packages explicitly enable ZIP64. Parquet is already Zstandard-compressed,
  so it is stored without a second compression pass; numbered KLARF files and
  the small manifest use DEFLATE. Already-compressed image files are stored
  without a second compression pass.
- Downloads stay in the browser's native download path. The API reads object
  storage in 1 MiB chunks, sends `Content-Length` and `Accept-Ranges`, and honors
  one HTTP byte range so interrupted large downloads can resume without loading
  the entire object into API or browser JavaScript memory.

ZIP generation temporarily holds Parquet, KLARF, resolved image files, and the
growing ZIP on API-local disk. Image bytes are written one resolved item at a
time rather than retained for the full Dataset. Production capacity planning
must reserve enough ephemeral disk for the largest concurrent packages.

## Performance benchmark

Use the checked-in 300,000-row benchmark to measure generation and the final
MinIO file upload together. The generated object is deleted after each sample:

```bash
make benchmark-sc-prediction-export ARGS="--format parquet --repeat 3"
make benchmark-sc-prediction-export ARGS="--format klarf --klarf-version 1.2 --repeat 3"
make benchmark-sc-prediction-export ARGS="--format klarf --klarf-version 1.8 --repeat 3"
```

The JSON report includes every wall-clock sample, median duration, output byte
count, and rows per second. This benchmark intentionally measures the current
API-local export path. Moving the operation to a Prefect CPU worker must also
measure scheduled-to-start latency on the target deployment; worker dispatch
time must not be hidden inside the writer throughput number.

## Object lifecycle

Prediction exports use the organization-scoped
`exports/orgs/{org_id}/...` object prefix. The download endpoint rejects objects
scoped to another organization before opening object storage. With MinIO
storage, the managed `exports/` lifecycle is required: the default configuration
expires exports after one day. On an unversioned MinIO bucket the same
`Expiration.Days` policy also removes abandoned multipart uploads; MinIO does
not persist the separate S3 `AbortIncompleteMultipartUpload` field. See MinIO's
[lifecycle rule pattern](https://docs.min.io/aistor/administration/object-lifecycle-management/lifecycle-rule-patterns/#abort-incomplete-multipart-uploads).
Run the production `prepare-platform` operation before serving traffic; it
reconciles this lifecycle rule and fails validation if the installed rule does
not match configuration. Operators changing retention should change
`storage.minio.lifecycle.exports` rather than creating an unrelated bucket rule.

Any ingress or load balancer placed in front of the bundled web Nginx must also
forward SSE without buffering and allow long-lived/streaming responses. The
bundled Nginx behavior alone cannot override an upstream proxy's shorter limit.
