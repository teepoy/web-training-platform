from __future__ import annotations

import asyncio
import os
import queue
import shutil
import threading
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, cast

import duckdb
import pyarrow as pa
import pyarrow.dataset as ds

from app.core.config import ScDataProviderConfig
from app.modules.sc.data_provider.materializer import MaterializedScScope
from app.modules.sc.data_provider.schemas import ScSqlParameter
from app.modules.sc.data_provider.sql_policy import ValidatedScSql


class ScQueryTimeoutError(TimeoutError):
    pass


class ScQueryResponseTooLargeError(RuntimeError):
    pass


class _StreamCancelledError(RuntimeError):
    pass


_STREAM_END = object()
_StreamItem = bytes | BaseException | object


@dataclass(frozen=True)
class PreparedArrowStream:
    body: AsyncGenerator[bytes, None]
    query_duration_ms: float
    close: Callable[[], Awaitable[None]]


class DuckDbQueryExecutor:
    def __init__(self, *, config: ScDataProviderConfig) -> None:
        self._config = config
        self._temp_directory = Path(config.cache_dir) / f"duckdb-temp-{os.getpid()}"
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="sc-duckdb-query",
        )
        self._lock = asyncio.Lock()
        self._connection = self._create_connection(config)

    def temp_directory_size_bytes(self) -> int:
        return sum(
            path.stat().st_size
            for path in self._temp_directory.rglob("*")
            if path.is_file()
        )

    async def close(self) -> None:
        await self._lock.acquire()
        try:
            await asyncio.get_running_loop().run_in_executor(
                self._executor, self._connection.close
            )
        finally:
            self._lock.release()
            await asyncio.to_thread(self._executor.shutdown, wait=True)
            await asyncio.to_thread(
                shutil.rmtree,
                self._temp_directory,
                ignore_errors=True,
            )

    async def prepare_stream(
        self,
        *,
        sql: ValidatedScSql,
        parameters: Sequence[ScSqlParameter],
        materialized: MaterializedScScope,
    ) -> PreparedArrowStream:
        await self._lock.acquire()
        started_at = time.monotonic()
        deadline = started_at + self._config.sql_timeout_seconds
        cancelled = threading.Event()
        output: queue.Queue[_StreamItem] = queue.Queue(
            maxsize=self._config.stream_queue_capacity
        )
        future = self._executor.submit(
            self._execute_to_queue,
            output,
            cancelled,
            deadline,
            sql,
            list(parameters),
            materialized,
        )
        try:
            first = await asyncio.wait_for(
                asyncio.to_thread(output.get),
                timeout=self._config.sql_timeout_seconds,
            )
        except TimeoutError as exc:
            cancelled.set()
            self._connection.interrupt()
            await asyncio.to_thread(_wait_future, future)
            self._lock.release()
            raise ScQueryTimeoutError("DuckDB query timed out") from exc
        except BaseException:
            cancelled.set()
            self._connection.interrupt()
            try:
                await asyncio.to_thread(_wait_future, future)
            finally:
                self._lock.release()
            raise

        if isinstance(first, BaseException):
            await asyncio.to_thread(_wait_future, future)
            self._lock.release()
            raise first
        if first is _STREAM_END:
            await asyncio.to_thread(_wait_future, future)
            self._lock.release()
            raise RuntimeError("DuckDB returned no Arrow stream header")

        query_duration_ms = (time.monotonic() - started_at) * 1000
        timeout_task: asyncio.Task[None] | None = None
        close_task: asyncio.Task[None] | None = None

        async def cleanup(*, cancel_timeout: bool) -> None:
            cancelled.set()
            if not future.done():
                self._connection.interrupt()
            if cancel_timeout and timeout_task is not None:
                timeout_task.cancel()
                with suppress(asyncio.CancelledError):
                    await timeout_task
            await asyncio.to_thread(_wait_future, future)
            self._lock.release()

        def ensure_close_task(*, cancel_timeout: bool) -> asyncio.Task[None]:
            nonlocal close_task
            if close_task is None:
                close_task = asyncio.create_task(
                    cleanup(cancel_timeout=cancel_timeout),
                    name="sc-duckdb-query-cleanup",
                )
            return close_task

        async def close() -> None:
            await asyncio.shield(ensure_close_task(cancel_timeout=True))

        async def close_at_deadline() -> None:
            await asyncio.sleep(max(0, deadline - time.monotonic()))
            # The response coroutine can remain blocked in ASGI send() after a
            # client disappears. Close independently at the query deadline so
            # one stalled transport cannot retain the worker's only connection
            # lock forever.
            await asyncio.shield(ensure_close_task(cancel_timeout=False))

        timeout_task = asyncio.create_task(
            close_at_deadline(),
            name="sc-duckdb-query-timeout",
        )

        async def body() -> AsyncGenerator[bytes, None]:
            try:
                yield cast(bytes, first)
                while True:
                    item = await asyncio.to_thread(output.get)
                    if item is _STREAM_END:
                        break
                    if isinstance(item, BaseException):
                        raise item
                    yield cast(bytes, item)
            finally:
                await close()

        return PreparedArrowStream(
            body=body(),
            query_duration_ms=query_duration_ms,
            close=close,
        )

    def _create_connection(
        self, config: ScDataProviderConfig
    ) -> duckdb.DuckDBPyConnection:
        self._temp_directory.mkdir(parents=True, exist_ok=True)
        connection = duckdb.connect(":memory:")
        connection.execute("SET memory_limit = ?", [config.duckdb_memory_limit])
        connection.execute("SET threads = ?", [config.duckdb_threads])
        connection.execute("SET temp_directory = ?", [str(self._temp_directory)])
        connection.execute(
            "SET max_temp_directory_size = ?",
            [config.duckdb_temp_directory_size],
        )
        connection.execute("SET autoinstall_known_extensions = false")
        connection.execute("SET autoload_known_extensions = false")
        connection.execute("SET python_enable_replacements = false")
        connection.execute("SET enable_external_access = false")
        connection.execute(
            "SET allocator_background_threads = ?",
            [config.duckdb_allocator_background_threads],
        )
        connection.execute(
            "SET preserve_insertion_order = ?",
            [config.duckdb_preserve_insertion_order],
        )
        connection.execute(
            "SET allocator_flush_threshold = ?",
            [config.duckdb_allocator_flush_threshold],
        )
        connection.execute(
            "SET allocator_bulk_deallocation_flush_threshold = ?",
            [config.duckdb_allocator_bulk_deallocation_flush_threshold],
        )
        return connection

    def _execute_to_queue(
        self,
        output: queue.Queue[_StreamItem],
        cancelled: threading.Event,
        deadline: float,
        sql: ValidatedScSql,
        parameters: list[ScSqlParameter],
        materialized: MaterializedScScope,
    ) -> None:
        registered = ["_samples_base", "_review_images"]
        if materialized.annotation_overlay is not None:
            registered.append("_annotation_overlay")
        if materialized.prediction_overlay is not None:
            registered.append("_prediction_overlay")
        try:
            self._register_scope(materialized)
            reader = self._connection.execute(sql.sql, parameters).to_arrow_reader(
                self._config.arrow_batch_rows
            )
            sink = _QueueSink(
                output=output,
                cancelled=cancelled,
                deadline=deadline,
                max_bytes=self._config.max_response_bytes,
                poll_interval=self._config.stream_queue_poll_interval_ms / 1000,
            )
            arrow_file = pa.PythonFile(cast(BinaryIO, sink), mode="w")
            with arrow_file, pa.ipc.new_stream(arrow_file, reader.schema) as writer:
                for batch in reader:
                    sink.check_active()
                    writer.write_batch(batch)
        except BaseException as exc:
            _put_stream_item(
                output,
                exc,
                cancelled,
                self._config.stream_queue_poll_interval_ms / 1000,
            )
        finally:
            cleanup_failed = cancelled.is_set()
            if not cleanup_failed:
                for view in ("samples", "review_images"):
                    try:
                        self._connection.execute(f"DROP VIEW IF EXISTS {view}")
                    except Exception:
                        cleanup_failed = True
                for name in registered:
                    try:
                        self._connection.unregister(name)
                    except Exception:
                        cleanup_failed = True
            try:
                if cleanup_failed:
                    self._replace_connection()
                else:
                    self._recycle_connection_under_memory_pressure()
            except BaseException as exc:
                _put_stream_item(
                    output,
                    exc,
                    cancelled,
                    self._config.stream_queue_poll_interval_ms / 1000,
                )
            _put_stream_item(
                output,
                _STREAM_END,
                cancelled,
                self._config.stream_queue_poll_interval_ms / 1000,
            )

    def _recycle_connection_under_memory_pressure(self) -> None:
        if self._current_rss_mb() < self._config.connection_recycle_rss_mb:
            return
        self._replace_connection()

    def _replace_connection(self) -> None:
        with suppress(Exception):
            self._connection.close()
        self._connection = self._create_connection(self._config)

    @staticmethod
    def _current_rss_mb(status_path: Path = Path("/proc/self/status")) -> float:
        try:
            for line in status_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
        except OSError:
            return 0
        return 0

    def _register_scope(self, materialized: MaterializedScScope) -> None:
        samples_dataset = ds.dataset(materialized.samples_base.path, format="parquet")
        if "row_key" not in samples_dataset.schema.names:
            raise RuntimeError(
                "SC samples cache is missing the required physical row_key column; "
                "rebuild the data-provider cache with the current materializer"
            )
        self._connection.register(
            "_samples_base",
            samples_dataset,
        )
        review_dataset = ds.dataset(materialized.review_images.path, format="parquet")
        self._connection.register("_review_images", review_dataset)
        if "row_key" not in review_dataset.schema.names:
            raise RuntimeError(
                "SC review-image cache is missing the required physical row_key column; "
                "rebuild the data-provider cache with the current materializer"
            )
        annotation_expression = "NULL::VARCHAR"
        annotation_join = ""
        if materialized.annotation_overlay is not None:
            self._connection.register(
                "_annotation_overlay",
                ds.dataset(materialized.annotation_overlay.path, format="parquet"),
            )
            annotation_expression = "annotation.annotation_label"
            annotation_join = (
                "LEFT JOIN _annotation_overlay AS annotation USING (row_key)"
            )

        prediction_label_expression = "NULL::VARCHAR"
        prediction_confidence_expression = "NULL::DOUBLE"
        prediction_join = ""
        if materialized.prediction_overlay is not None:
            self._connection.register(
                "_prediction_overlay",
                ds.dataset(materialized.prediction_overlay.path, format="parquet"),
            )
            prediction_label_expression = "prediction.prediction_label"
            prediction_confidence_expression = "prediction.prediction_confidence"
            prediction_join = (
                "LEFT JOIN _prediction_overlay AS prediction USING (row_key)"
            )
        self._connection.execute(
            f"""
            CREATE TEMP VIEW samples AS
            SELECT
                base.* EXCLUDE (
                    annotation_label,
                    prediction_label,
                    prediction_confidence,
                    final_class
                ),
                {annotation_expression} AS annotation_label,
                {prediction_label_expression} AS prediction_label,
                {prediction_confidence_expression} AS prediction_confidence,
                CASE
                    WHEN {annotation_expression} IS NOT NULL
                         AND {annotation_expression} NOT IN ('', '0')
                    THEN {annotation_expression}
                    ELSE {prediction_label_expression}
                END AS final_class
            FROM _samples_base AS base
            {annotation_join}
            {prediction_join}
            """
        )
        self._connection.execute(
            """
            CREATE TEMP VIEW review_images AS
            SELECT images.*
            FROM _review_images AS images
            INNER JOIN _samples_base AS base USING (row_key)
            """
        )


class _QueueSink:
    def __init__(
        self,
        *,
        output: queue.Queue[_StreamItem],
        cancelled: threading.Event,
        deadline: float,
        max_bytes: int,
        poll_interval: float,
    ) -> None:
        self._output = output
        self._cancelled = cancelled
        self._deadline = deadline
        self._max_bytes = max_bytes
        self._poll_interval = poll_interval
        self._written = 0
        self._position = 0
        self.closed = False

    def writable(self) -> bool:
        return True

    def write(self, data: bytes | memoryview) -> int:
        self.check_active()
        payload = bytes(data)
        next_size = self._written + len(payload)
        if next_size > self._max_bytes:
            raise ScQueryResponseTooLargeError(
                f"Arrow response exceeded {self._max_bytes} bytes"
            )
        _put_stream_item(
            self._output,
            payload,
            self._cancelled,
            self._poll_interval,
        )
        self._written = next_size
        self._position += len(payload)
        return len(payload)

    def tell(self) -> int:
        return self._position

    def flush(self) -> None:
        self.check_active()

    def close(self) -> None:
        self.closed = True

    def check_active(self) -> None:
        if self._cancelled.is_set():
            raise _StreamCancelledError("Arrow stream was cancelled")
        if time.monotonic() >= self._deadline:
            raise ScQueryTimeoutError("DuckDB query timed out")


def _put_stream_item(
    output: queue.Queue[_StreamItem],
    item: _StreamItem,
    cancelled: threading.Event,
    poll_interval: float,
) -> None:
    while True:
        if cancelled.is_set():
            with suppress(queue.Full):
                output.put_nowait(item)
            return
        try:
            output.put(item, timeout=poll_interval)
            return
        except queue.Full:
            continue


def _wait_future(future: Future[None]) -> None:
    with suppress(BaseException):
        future.result()
