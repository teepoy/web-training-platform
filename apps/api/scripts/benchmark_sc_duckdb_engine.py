"""Run the SC DuckDB/Arrow engine contract against 300,000 generated rows."""

from __future__ import annotations

import asyncio
import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from app.core.config import load_config
from app.modules.sc.data_provider.cache import CachedDataObject
from app.modules.sc.data_provider.engine import DuckDbQueryExecutor
from app.modules.sc.data_provider.materializer import MaterializedScScope
from app.modules.sc.data_provider.schemas import ScSqlParameter
from app.modules.sc.data_provider.scope import ScDataScope
from app.modules.sc.data_provider.sql_policy import validate_sc_sql


def _cached(path: Path, table: pa.Table, object_id: str) -> CachedDataObject:
    pq.write_table(table, path)
    return CachedDataObject(
        object_id=object_id,
        path=path,
        size_bytes=path.stat().st_size,
        scope="benchmark",
        revision=0,
        cache_status="miss",
    )


def _materialized(
    root: Path,
    *,
    row_count: int,
    fixture_batch_rows: int,
) -> MaterializedScScope:
    samples_path = root / "samples.parquet"
    writer: pq.ParquetWriter | None = None
    try:
        for start in range(0, row_count, fixture_batch_rows):
            end = min(start + fixture_batch_rows, row_count)
            batch_rows = end - start
            table = pa.table(
                {
                    "defect_id": pa.array(range(start + 1, end + 1), type=pa.int32()),
                    "wafer_x": pa.array(
                        (index % 150_000_000 for index in range(start, end))
                    ),
                    "wafer_y": pa.array(
                        (index % 150_000_000 for index in range(start, end))
                    ),
                    "class_number": pa.array(
                        (index % 100 for index in range(start, end))
                    ),
                    "rough_bin": pa.array((index % 50 for index in range(start, end))),
                    "annotation_label": pa.nulls(batch_rows, type=pa.string()),
                    "prediction_label": pa.nulls(batch_rows, type=pa.string()),
                    "prediction_confidence": pa.nulls(batch_rows, type=pa.float64()),
                    "final_class": pa.nulls(batch_rows, type=pa.string()),
                }
            )
            writer = writer or pq.ParquetWriter(samples_path, table.schema)
            writer.write_table(table)
    finally:
        if writer is not None:
            writer.close()
    samples = CachedDataObject(
        object_id="samples",
        path=samples_path,
        size_bytes=samples_path.stat().st_size,
        scope="benchmark",
        revision=0,
        cache_status="miss",
    )
    return MaterializedScScope(
        scope=ScDataScope.inspection(
            inspection_time="2026-01-01T00:00:00",
            wafer_key=1,
            org_id="benchmark",
        ),
        revision=0,
        samples_base=samples,
        review_images=_cached(
            root / "review-images.parquet",
            pa.table(
                {
                    "defect_id": pa.array([], type=pa.int32()),
                    "image_id": pa.array([], type=pa.int64()),
                }
            ),
            "review-images",
        ),
        annotation_overlay=None,
        prediction_overlay=None,
    )


async def _measure(
    executor: DuckDbQueryExecutor,
    materialized: MaterializedScScope,
    sql: str,
    parameters: list[ScSqlParameter],
) -> tuple[float, int]:
    started = time.perf_counter()
    stream = await executor.prepare_stream(
        sql=validate_sc_sql(sql),
        parameters=parameters,
        materialized=materialized,
    )
    payload = b"".join([chunk async for chunk in stream.body])
    return (time.perf_counter() - started) * 1000, len(payload)


def _rss_mb() -> float:
    import resource

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return rss / divisor


async def _run(args: argparse.Namespace) -> None:
    with tempfile.TemporaryDirectory(prefix="sc-duckdb-benchmark-") as raw_root:
        root = Path(raw_root)
        materialized = _materialized(
            root,
            row_count=args.rows,
            fixture_batch_rows=args.fixture_batch_rows,
        )
        config = load_config(skip_runtime_validation=True).sc.data_provider.model_copy(
            update={"cache_dir": str(root)}
        )
        executor = DuckDbQueryExecutor(config=config)
        queries: dict[str, tuple[str, list[ScSqlParameter]]] = {
            "rectangle_count": (
                "SELECT count(*) FROM samples WHERE wafer_x BETWEEN ? AND ? "
                "AND wafer_y BETWEEN ? AND ?",
                [-75_000_000, 75_000_000, -75_000_000, 75_000_000],
            ),
            "class_count": (
                "SELECT count(*) FROM samples WHERE class_number = ?",
                [42],
            ),
            "id_selection": (
                "SELECT defect_id FROM samples WHERE defect_id = ANY(?) "
                "ORDER BY defect_id",
                [list(range(1, 1001))],
            ),
            "page": (
                "SELECT defect_id, rough_bin FROM samples "
                "WHERE wafer_x BETWEEN ? AND ? AND wafer_y BETWEEN ? AND ? "
                "ORDER BY defect_id LIMIT ? OFFSET ?",
                [-75_000_000, 75_000_000, -75_000_000, 75_000_000, 10, 10],
            ),
            "random_sample": (
                "SELECT defect_id FROM samples WHERE class_number = ? "
                "ORDER BY RANDOM() LIMIT ?",
                [42, 10],
            ),
        }
        report: dict[str, object] = {
            "pid": os.getpid(),
            "rows": args.rows,
            "iterations": args.iterations,
        }
        try:
            for name, (sql, parameters) in queries.items():
                cold_ms, response_bytes = await _measure(
                    executor, materialized, sql, parameters
                )
                warm = [
                    (await _measure(executor, materialized, sql, parameters))[0]
                    for _iteration in range(args.iterations)
                ]
                report[name] = {
                    "cold_ms": cold_ms,
                    "warm_p50_ms": statistics.median(warm),
                    "warm_p95_ms": sorted(warm)[round((len(warm) - 1) * 0.95)],
                    "response_bytes": response_bytes,
                }
            report["rss_mb"] = _rss_mb()
            report["duckdb_temp_bytes"] = executor.temp_directory_size_bytes()
            cancelled = await executor.prepare_stream(
                sql=validate_sc_sql("SELECT * FROM samples ORDER BY defect_id"),
                parameters=[],
                materialized=materialized,
            )
            await anext(cancelled.body)
            await cancelled.body.aclose()
            recovery_ms, _ = await _measure(
                executor,
                materialized,
                "SELECT count(*) FROM samples",
                [],
            )
            report["client_disconnect_recovery_ms"] = recovery_ms
        finally:
            await executor.close()
        print(json.dumps(report, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rows", type=int, choices=(300_000, 1_000_000), default=300_000
    )
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--fixture-batch-rows", type=int, default=50_000)
    args = parser.parse_args()
    if args.iterations < 2:
        parser.error("--iterations must be at least 2")
    if args.fixture_batch_rows <= 0:
        parser.error("--fixture-batch-rows must be positive")
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
