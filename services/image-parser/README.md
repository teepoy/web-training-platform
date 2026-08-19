# Image resolution service and local resolvers

Image resolution is composed from three independent concerns:

1. `filesource` exposes an already-local regular file or directory. A mounted
   SMB share is a borrowed directory source. It enforces rooted access and
   rejects absolute caller paths, traversal, and symlinks that escape the root.
2. `sourceformat` selects one code-registered format driver. Drivers own layout
   and container rules; the generic source layer does not assume ZIP, index
   ranges, or any particular image file type.
3. An optional entrypoint-owned stager makes source objects local before the
   driver runs. Staging, retry, cache lifecycle, cleanup, credentials, and
   concurrency budgets are not shared policy.

Dataset metadata stores `filesystem.image-source.v1` plus a format ID. It never
stores an absolute root, SMB credentials, object-store credentials, staging
mode, cache policy, or cleanup ownership. `IMAGE_SOURCE_PROFILES_JSON` and
`SC_COMPAT_IMAGE_SOURCE_PROFILE` no longer exist.

## Entrypoints

### Display server

`cmd/server` runs HTTP/gRPC display APIs. Its SC compatibility path is composed
in code from:

- a shared-cache directory below `CACHE_DIR`;
- the SC upstream stager;
- the optional `sc.legacy-range-zip.v1` format driver.

The display server does not expose the job batch `ResolvePatchImages` RPC.
Training and prediction therefore cannot consume display capacity by mistake.
The shared cache uses `CACHE_TTL`, `CACHE_CLEANUP_INTERVAL`, and
`CACHE_MAX_BYTES`; reads refresh mtime, and cleanup evicts expired then
least-recently-used files.

### Train/batch-predict job resolver

`cmd/batch-resolve` builds `/usr/local/bin/image-parser-batch` in the GPU worker.
One child is opened for one training materialization or batch prediction job and
reused for all ordered bounded requests. It stages upstream objects into a
job-owned directory, resolves them locally, then removes that directory on
exit. It never opens HTTP/gRPC listeners or falls back to the display server.

The framing protocol is a four-byte big-endian size followed by a
`ResolvePatchImagesRequest`; the response is a length-prefixed
`ResolvePatchImagesBatchResponse`. Frames are capped at 256 MiB. Configure the
parent directory with `SC_JOB_IMAGE_RESOLVER_CACHE_ROOT`; the per-job directory
is deleted when the resolver process exits.

### Pure-local resolver

`cmd/local-resolve` uses the same framed protocol without initializing an
upstream or S3 client and without a stager. It requires:

| Variable              | Meaning                                                            |
| --------------------- | ------------------------------------------------------------------ |
| `IMAGE_SOURCE_ROOT`   | Absolute local file/directory or mounted SMB root.                 |
| `IMAGE_SOURCE_KIND`   | `directory` (default) or `file`.                                   |
| `IMAGE_SOURCE_FORMAT` | Code-registered format ID, for example `filesystem.role-paths.v1`. |

The source is borrowed and is never deleted. Use this entrypoint for
local-source jobs and online/instant prediction hosts. The worker can switch to
it with `SC_JOB_IMAGE_RESOLVER_BINARY=/usr/local/bin/image-parser-local` and the
three variables above.

For host development, `make prefect-worker-gpu-host` selects the staged batch
entrypoint and `make prefect-worker-gpu-local-host` selects the pure-local
entrypoint. They build different output files, so one target cannot silently
overwrite the resolver selected by the other.

## Format drivers

`filesystem.role-paths.v1` reads the data row's explicit role-relative paths
and invents no layout. It supports a single file or a directory source. A
caller selecting this format must supply `role_paths` for every requested role;
it does not need SC inspection, wafer, or defect identity. Current legacy SC
rows instead select `sc.legacy-range-zip.v1`, which derives its locators from
that compatibility identity.

`sc.legacy-range-zip.v1` is a compatibility driver. Only this package knows the
old `<YYYYMMDD_HHMMSS>/<wafer_key>/<start>-<end>.zip`, 500-defect range, and ZIP
member naming rules. These rules are not part of the generic source contract.
Archives are opened once per bounded batch and resolved concurrently across at
most eight archives.

New file/container formats must be implemented as another explicit driver and
registered in code. Drivers never sniff extensions and never fall back to a
different format after failure.

## Source ownership

- `borrowed`: local/SMB source; resolver cannot write or delete it.
- `job_owned`: a job stager may write it and job shutdown deletes it.
- `shared_cache`: a service stager may write it and the cache janitor owns
  eviction; the resolver cannot delete the root.

## External connections

The display server and upstream-staging job resolver use `SC_UPSTREAM_ADDR` for
metadata. Patch and review object stores use `SC_PATCH_S3_*` and
`SC_REVIEW_S3_*` (`ENDPOINT`, `REGION`, `ACCESS_KEY`, `SECRET_KEY`), with the
corresponding `MINIO_*` values as deployment defaults. The pure-local resolver
does not initialize these clients.

`GRPC_LISTEN` on the display server accepts `tcp://<address>` or
`unix:///absolute/socket/path`. A Unix listener removes only a stale socket and
refuses to replace a regular file.
