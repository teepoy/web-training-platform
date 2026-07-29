# Image parser

The image parser keeps its existing in-memory ZIP LRU and can attach a local
file-cache helper as a second cache tier. Local cache files use a SHA-256 digest
of the S3 bucket/key as their filename; the original object name is not written
to disk.

## Local file cache

| Environment variable       | Meaning                                                                 |
| -------------------------- | ----------------------------------------------------------------------- |
| `CACHE_SIZE_MB`            | Existing in-memory LRU limit in MiB.                                    |
| `CACHE_DIR`                | Cache directory.                                                        |
| `CACHE_TTL`                | Expiry duration since the program last successfully read the file.      |
| `CACHE_CLEANUP_INTERVAL`   | Interval between full directory scans.                                  |
| `CACHE_MAX_BYTES`          | Optional byte limit. `0` disables capacity eviction.                    |

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
