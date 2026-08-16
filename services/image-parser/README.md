# Image parser

The image parser keeps its existing in-memory ZIP LRU and can attach a local
file-cache helper as a second cache tier. Local cache files use a SHA-256 digest
of the S3 bucket/key as their filename; the original object name is not written
to disk.

## Patch archive source profiles

The long-running gRPC server resolves prediction images through one provider
registry. `IMAGE_SOURCE_PROFILES_JSON` is required and maps deployment-owned
profile names to providers. `SC_COMPAT_IMAGE_SOURCE_PROFILE` is also required;
it selects the configured profile used only by the older SC image RPCs.

```json
{
  "sc_upstream": { "provider": "sc_upstream" },
  "mounted_archive": {
    "provider": "sc_patch_zip_folder",
    "root": "/mnt/sc-patch-archives"
  }
}
```

`sc_upstream` resolves archive references through the SC upstream service.
`sc_patch_zip_folder` reads a local directory or an SMB share mounted into the
container. Its v1 layout is
`<root>/<YYYYMMDD_HHMMSS>/<wafer_key>/<start:06d>-<end:06d>.zip`, with 500
defects per ZIP. The root and credentials stay in deployment configuration;
RPC callers provide only a profile name and SC identity. Absolute caller paths,
directory traversal, and symlinks escaping the configured root are rejected.
Providers never fall back to another provider after a failure.

`ResolvePatchImages` accepts one source profile, requested patch roles, and a
bounded list of correlated samples. It streams one result per sample and role.
Missing/corrupt archives or entries are stable item errors; an unknown profile,
invalid request, or unavailable source is an RPC error.

## Offline training batch process

`cmd/batch-resolve` builds the `image-parser-batch` executable shipped inside
the GPU Prefect worker. One process is started for one training materialization
and reused for every ordered 512-row batch. It reads a 4-byte big-endian frame
length followed by `ResolvePatchImagesRequest` protobuf bytes from stdin, then
writes one length-prefixed `ResolvePatchImagesBatchResponse` to stdout. The
process does not listen on HTTP/gRPC and never falls back to the online
image-parser service.

The process reads the same `IMAGE_SOURCE_PROFILES_JSON` and
`SC_COMPAT_IMAGE_SOURCE_PROFILE` registry as the server. Its cache is scoped to
the training job and removed on exit; configure it with
`SC_TRAINING_IMAGE_PARSER_CACHE_ROOT` and
`SC_TRAINING_IMAGE_PARSER_CACHE_SIZE_MB`. A folder profile must be mounted
read-only at the same absolute path in both the image-parser and GPU worker
containers.

`GRPC_LISTEN` accepts `tcp://<address>` or `unix:///absolute/socket/path`. If it
is absent, the compatibility `GRPC_PORT` setting is used. A Unix listener only
removes a stale socket; it refuses to replace a regular file.

## Data source connections

`SC_UPSTREAM_ADDR` selects the SC metadata service. Patch and review object
stores use `SC_PATCH_S3_*` and `SC_REVIEW_S3_*` respectively (`ENDPOINT`,
`REGION`, `ACCESS_KEY`, and `SECRET_KEY`). Missing source-specific values fall
back to the corresponding `MINIO_*` setting. The repository mock addresses and
credentials are used only when neither deployment setting is present. This
same environment contract is inherited by the offline training batch process,
which lets a host worker use `127.0.0.1` endpoints while Compose uses service
DNS names.

## Local file cache

| Environment variable     | Meaning                                                            |
| ------------------------ | ------------------------------------------------------------------ |
| `CACHE_SIZE_MB`          | Existing in-memory LRU limit in MiB.                               |
| `CACHE_DIR`              | Cache directory.                                                   |
| `CACHE_TTL`              | Expiry duration since the program last successfully read the file. |
| `CACHE_CLEANUP_INTERVAL` | Interval between full directory scans.                             |
| `CACHE_MAX_BYTES`        | Optional byte limit. `0` disables capacity eviction.               |

Durations use Go duration syntax such as `10m`, `2h`, or `30s`. Invalid values
fail service startup.

Lookup order is in-memory LRU, local file helper, then S3. A local file hit is
promoted back into the in-memory LRU. Every successful local read updates the
file mtime. Startup and periodic cleanup
scan the whole directory, remove files whose mtime is older than `CACHE_TTL`,
then, when `CACHE_MAX_BYTES` is greater than zero, remove the least recently
used files until the directory is within the configured limit.

Writes use a temporary file followed by an atomic rename. Files not created by
the cache are ignored. A stale interrupted temporary write is removed after one
TTL window.
