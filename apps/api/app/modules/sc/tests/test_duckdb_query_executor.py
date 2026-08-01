from __future__ import annotations

import asyncio
import os
import queue
import threading
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.core.config import load_config
from app.modules.sc.data_provider.cache import CachedDataObject
from app.modules.sc.data_provider.engine import (
    DuckDbQueryExecutor,
    ScQueryResponseTooLargeError,
)
from app.modules.sc.data_provider.materializer import MaterializedScScope
from app.modules.sc.data_provider.schemas import ScSqlParameter
from app.modules.sc.data_provider.scope import ScDataScope
from app.modules.sc.data_provider.sql_policy import ValidatedScSql, validate_sc_sql


def _cached_table(path: Path, table: pa.Table, *, object_id: str) -> CachedDataObject:
    pq.write_table(table, path)
    return CachedDataObject(
        object_id=object_id,
        path=path,
        size_bytes=path.stat().st_size,
        scope="test",
        revision=0,
        cache_status="miss",
    )


def _materialized(tmp_path: Path) -> MaterializedScScope:
    samples = _cached_table(
        tmp_path / "samples.parquet",
        pa.table(
            {
                "defect_id": [1, 2, 3],
                "rough_bin": [10, 20, 20],
                "annotation_label": [None, None, None],
                "prediction_label": [None, None, None],
                "prediction_confidence": [None, None, None],
                "final_class": [None, None, None],
            }
        ),
        object_id="samples",
    )
    review_images = _cached_table(
        tmp_path / "review-images.parquet",
        pa.table({"defect_id": [2], "image_id": [100]}),
        object_id="review-images",
    )
    return MaterializedScScope(
        scope=ScDataScope.inspection(
            inspection_time="2026-01-01T00:00:00Z",
            wafer_key=1,
            org_id="org",
        ),
        revision=0,
        samples_base=samples,
        review_images=review_images,
        annotation_overlay=None,
        prediction_overlay=None,
    )


@pytest.mark.asyncio
async def test_executes_parameterized_query_as_arrow_stream(tmp_path: Path) -> None:
    config = load_config(skip_runtime_validation=True).sc.data_provider.model_copy(
        update={"cache_dir": str(tmp_path)}
    )
    executor = DuckDbQueryExecutor(config=config)
    try:
        prepared = await executor.prepare_stream(
            sql=validate_sc_sql(
                "SELECT defect_id FROM samples WHERE rough_bin = ? ORDER BY defect_id"
            ),
            parameters=[20],
            materialized=_materialized(tmp_path),
        )
        payload = b"".join([chunk async for chunk in prepared.body])
    finally:
        await executor.close()

    result = pa.ipc.open_stream(payload).read_all()
    assert result.to_pydict() == {"defect_id": [2, 3]}


@pytest.mark.asyncio
async def test_joins_annotation_and_prediction_overlays_independently(
    tmp_path: Path,
) -> None:
    materialized = _materialized(tmp_path)
    annotation = _cached_table(
        tmp_path / "annotations.parquet",
        pa.table({"defect_id": [2], "annotation_label": ["manual"]}),
        object_id="annotations",
    )
    prediction = _cached_table(
        tmp_path / "predictions.parquet",
        pa.table(
            {
                "defect_id": [1, 2],
                "prediction_label": ["predicted", "ignored"],
                "prediction_confidence": [0.9, 0.8],
            }
        ),
        object_id="predictions",
    )
    materialized = replace(
        materialized,
        annotation_overlay=annotation,
        prediction_overlay=prediction,
    )
    config = load_config(skip_runtime_validation=True).sc.data_provider.model_copy(
        update={"cache_dir": str(tmp_path)}
    )
    executor = DuckDbQueryExecutor(config=config)
    try:
        prepared = await executor.prepare_stream(
            sql=validate_sc_sql(
                "SELECT defect_id, annotation_label, prediction_label, final_class "
                "FROM samples ORDER BY defect_id"
            ),
            parameters=[],
            materialized=materialized,
        )
        payload = b"".join([chunk async for chunk in prepared.body])
    finally:
        await executor.close()

    assert pa.ipc.open_stream(payload).read_all().to_pydict() == {
        "defect_id": [1, 2, 3],
        "annotation_label": [None, "manual", None],
        "prediction_label": ["predicted", "ignored", None],
        "final_class": ["predicted", "manual", None],
    }


@pytest.mark.asyncio
async def test_rejects_response_larger_than_configured_limit(tmp_path: Path) -> None:
    config = load_config(skip_runtime_validation=True).sc.data_provider.model_copy(
        update={"cache_dir": str(tmp_path), "max_response_bytes": 1}
    )
    executor = DuckDbQueryExecutor(config=config)
    try:
        with pytest.raises(ScQueryResponseTooLargeError):
            await executor.prepare_stream(
                sql=validate_sc_sql("SELECT * FROM samples"),
                parameters=[],
                materialized=_materialized(tmp_path),
            )
    finally:
        await executor.close()


@pytest.mark.asyncio
async def test_closing_stream_early_releases_worker_and_temp_directory(
    tmp_path: Path,
) -> None:
    config = load_config(skip_runtime_validation=True).sc.data_provider.model_copy(
        update={"cache_dir": str(tmp_path), "arrow_batch_rows": 1}
    )
    executor = DuckDbQueryExecutor(config=config)
    prepared = await executor.prepare_stream(
        sql=validate_sc_sql("SELECT * FROM samples"),
        parameters=[],
        materialized=_materialized(tmp_path),
    )
    await anext(prepared.body)
    await prepared.body.aclose()

    second = await executor.prepare_stream(
        sql=validate_sc_sql("SELECT count(*) AS row_count FROM samples"),
        parameters=[],
        materialized=_materialized(tmp_path),
    )
    payload = b"".join([chunk async for chunk in second.body])
    temp_directory = tmp_path / f"duckdb-temp-{os.getpid()}"
    assert temp_directory.is_dir()
    await executor.close()

    assert pa.ipc.open_stream(payload).read_all().to_pydict() == {"row_count": [3]}
    assert not temp_directory.exists()


@pytest.mark.asyncio
async def test_closing_prepared_stream_before_iteration_releases_worker(
    tmp_path: Path,
) -> None:
    config = load_config(skip_runtime_validation=True).sc.data_provider.model_copy(
        update={"cache_dir": str(tmp_path), "arrow_batch_rows": 1}
    )
    executor = DuckDbQueryExecutor(config=config)
    prepared = await executor.prepare_stream(
        sql=validate_sc_sql("SELECT * FROM samples"),
        parameters=[],
        materialized=_materialized(tmp_path),
    )
    await prepared.close()

    second = await executor.prepare_stream(
        sql=validate_sc_sql("SELECT count(*) AS row_count FROM samples"),
        parameters=[],
        materialized=_materialized(tmp_path),
    )
    payload = b"".join([chunk async for chunk in second.body])
    await executor.close()

    assert pa.ipc.open_stream(payload).read_all().to_pydict() == {"row_count": [3]}


@pytest.mark.asyncio
async def test_cancelled_blocked_producer_recycles_connection_catalog(
    tmp_path: Path,
) -> None:
    config = load_config(skip_runtime_validation=True).sc.data_provider.model_copy(
        update={
            "cache_dir": str(tmp_path),
            "arrow_batch_rows": 1,
            "stream_queue_capacity": 1,
        }
    )
    materialized = _materialized(tmp_path)
    executor = DuckDbQueryExecutor(config=config)
    prepared = await executor.prepare_stream(
        sql=validate_sc_sql(
            "SELECT left_samples.defect_id "
            "FROM samples AS left_samples CROSS JOIN samples AS right_samples"
        ),
        parameters=[],
        materialized=materialized,
    )
    await prepared.close()

    second = await executor.prepare_stream(
        sql=validate_sc_sql("SELECT count(*) AS row_count FROM samples"),
        parameters=[],
        materialized=materialized,
    )
    payload = b"".join([chunk async for chunk in second.body])
    await executor.close()

    assert pa.ipc.open_stream(payload).read_all().to_pydict() == {"row_count": [3]}


@pytest.mark.asyncio
async def test_unconsumed_stream_releases_worker_at_query_deadline(
    tmp_path: Path,
) -> None:
    config = load_config(skip_runtime_validation=True).sc.data_provider.model_copy(
        update={
            "cache_dir": str(tmp_path),
            "arrow_batch_rows": 1,
            "sql_timeout_seconds": 1,
        }
    )
    executor = DuckDbQueryExecutor(config=config)
    first = await executor.prepare_stream(
        sql=validate_sc_sql("SELECT * FROM samples"),
        parameters=[],
        materialized=_materialized(tmp_path),
    )

    await asyncio.sleep(1.1)
    second = await asyncio.wait_for(
        executor.prepare_stream(
            sql=validate_sc_sql("SELECT count(*) AS row_count FROM samples"),
            parameters=[],
            materialized=_materialized(tmp_path),
        ),
        timeout=1,
    )
    payload = b"".join([chunk async for chunk in second.body])
    await first.close()
    await executor.close()

    assert pa.ipc.open_stream(payload).read_all().to_pydict() == {"row_count": [3]}


@pytest.mark.asyncio
async def test_cancelling_before_first_arrow_chunk_releases_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config(skip_runtime_validation=True).sc.data_provider.model_copy(
        update={"cache_dir": str(tmp_path)}
    )
    executor = DuckDbQueryExecutor(config=config)
    original_execute = executor._execute_to_queue
    started = threading.Event()

    def wait_for_cancel(
        output: queue.Queue[object],
        cancelled: threading.Event,
        deadline: float,
        sql: ValidatedScSql,
        parameters: Sequence[ScSqlParameter],
        materialized: MaterializedScScope,
    ) -> None:
        del deadline, sql, parameters, materialized
        started.set()
        cancelled.wait(timeout=2)
        output.put(RuntimeError("cancelled before first Arrow chunk"))

    monkeypatch.setattr(executor, "_execute_to_queue", wait_for_cancel)
    pending = asyncio.create_task(
        executor.prepare_stream(
            sql=validate_sc_sql("SELECT * FROM samples"),
            parameters=[],
            materialized=_materialized(tmp_path),
        )
    )
    assert await asyncio.to_thread(started.wait, 1)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending

    monkeypatch.setattr(executor, "_execute_to_queue", original_execute)
    second = await executor.prepare_stream(
        sql=validate_sc_sql("SELECT count(*) AS row_count FROM samples"),
        parameters=[],
        materialized=_materialized(tmp_path),
    )
    payload = b"".join([chunk async for chunk in second.body])
    await executor.close()

    assert pa.ipc.open_stream(payload).read_all().to_pydict() == {"row_count": [3]}


@pytest.mark.asyncio
async def test_recycles_connection_after_stream_when_rss_exceeds_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config(skip_runtime_validation=True).sc.data_provider.model_copy(
        update={"cache_dir": str(tmp_path), "connection_recycle_rss_mb": 1}
    )
    executor = DuckDbQueryExecutor(config=config)
    original_connection = executor._connection
    monkeypatch.setattr(executor, "_current_rss_mb", lambda: 2)
    prepared = await executor.prepare_stream(
        sql=validate_sc_sql("SELECT count(*) AS row_count FROM samples"),
        parameters=[],
        materialized=_materialized(tmp_path),
    )
    payload = b"".join([chunk async for chunk in prepared.body])
    try:
        assert executor._connection is not original_connection
        assert pa.ipc.open_stream(payload).read_all().to_pydict() == {
            "row_count": [3]
        }
    finally:
        await executor.close()
