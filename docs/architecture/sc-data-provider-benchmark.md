# SC Data Provider Migration Benchmark

## Checked-in 300,000-row baseline

Measured on 2026-08-01 on Darwin arm64. These are local in-process migration
numbers, not a production SLO. Both runs used 10 warm iterations.

| Operation           | Perspective avg | Perspective min | DuckDB/Arrow cold | DuckDB/Arrow warm p50 | DuckDB/Arrow warm p95 |
| ------------------- | --------------: | --------------: | ----------------: | --------------------: | --------------------: |
| Rectangle           |      273.067 ms |      253.482 ms |          8.260 ms |              3.851 ms |              4.881 ms |
| Class filter        |       47.861 ms |       40.529 ms |          2.295 ms |              2.332 ms |              2.410 ms |
| 1,000-ID selection  |     1083.454 ms |     1003.581 ms |          8.605 ms |              3.160 ms |              3.526 ms |
| Ordered page of 10  |      408.687 ms |      368.691 ms |          6.027 ms |              4.662 ms |              5.213 ms |
| Random sample of 10 |       43.958 ms |       40.935 ms |          2.932 ms |              2.601 ms |              2.919 ms |

The DuckDB run reported 278.84 MiB process RSS and zero spill bytes. Arrow
responses were 304 bytes for count queries, 4,288 bytes for the 1,000-ID
projection, 512 bytes for the page, and 328 bytes for the random sample.

The Perspective benchmark included its view materialization/export behavior;
the DuckDB benchmark includes Parquet scan, SQL execution, Arrow stream writing,
bounded queue transfer, and Arrow body collection. The absolute numbers are not
directly equivalent to browser end-to-end latency, but they preserve the
previous implementation baseline before the Perspective package was removed.

## Post-remediation 300,000-row engine check

Measured on 2026-08-01 on Darwin arm64 after bounded cache construction,
independent annotation/prediction overlays, allocator tuning, and connection
recycling were added. The command used 10 warm iterations:

```text
uv run --directory apps/api python scripts/benchmark_sc_duckdb_engine.py \
  --rows 300000 --iterations 10
```

| Operation           |      Cold | Warm p50 | Warm p95 | Arrow bytes |
| ------------------- | --------: | -------: | -------: | ----------: |
| Rectangle count     | 10.557 ms | 4.845 ms | 5.818 ms |         304 |
| Class count         |  3.142 ms | 2.894 ms | 3.149 ms |         304 |
| 1,000-ID selection  |  4.181 ms | 3.609 ms | 3.878 ms |       4,288 |
| Ordered page of 10  |  6.107 ms | 5.518 ms | 6.446 ms |         512 |
| Random sample of 10 |  3.433 ms | 3.375 ms | 3.778 ms |         328 |

The fixture Parquet was generated in bounded 50,000-row batches. Process
high-water RSS was 263.27 MiB, DuckDB spill remained zero, and a
deliberately closed Arrow stream was followed by a successful count query in
3.554 ms. A three-iteration 1M-row check completed with zero spill and a
362.61 MiB process high-water mark. This is a synthetic in-process regression
check; its RSS includes DuckDB scan buffers and does not replace
the four-worker HTTP/cgroup acceptance run.

## Production-shaped HTTP run

After starting the Compose stack, use an authenticated dataset scope:

```text
uv run --directory apps/api --extra dev python scripts/benchmark_sc_data_provider.py \
  --query-url http://localhost:8001/api/v1/sc/data/datasets/DATASET_ID/query \
  --events-url http://localhost:8001/api/v1/sc/data/datasets/DATASET_ID/events \
  --health-url http://localhost:8001/health \
  --sql 'SELECT defect_id, rough_bin FROM samples ORDER BY defect_id LIMIT ?' \
  --parameters-json '[300000]' \
  --token TOKEN \
  --org-id ORG_ID \
  --iterations 30 \
  --reconnect-cycles 100 \
  --disconnect-cycles 5 \
  --cgroup api=/sys/fs/cgroup/API_PATH \
  --cgroup provider=/sys/fs/cgroup/PROVIDER_PATH
```

Acceptance requires:

- warm requests reach more than one `X-SC-Worker-PID` in the four-worker
  Compose service;
- every response reports the same current revision regardless of worker;
- cold/warm p50 and p95, response bytes, cache state, and spill are recorded;
- 100 SSE reconnect/query cycles do not show sustained RSS or temp growth;
- cache hits remain valid after a worker restart and old revisions disappear
  only after their leases end.

The checked-in local environment did not have the external PostgreSQL, Redis,
SC upstream, and authenticated dataset fixture needed to produce an honest
four-worker HTTP number. The harness and production-shaped deployment are part
of the repository so that result can be recorded against the target client
environment instead of substituting a synthetic network number.
