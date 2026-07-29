from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import datetime
from typing import Any, cast

import polars as pl
from fastapi import WebSocket
from perspective import Client, Server, Table
from starlette.websockets import WebSocketDisconnect

from app.modules.sc.domain.models import _coerce_naive_to_upstream_tz
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.shared.infrastructure.redis.event_publisher import (
    ANNOTATION_CHANNEL,
    PREDICTION_CHANNEL,
)

_logger = logging.getLogger(__name__)

_MAX_PENDING_RESPONSES = 16
_MAX_PENDING_RESPONSE_BYTES = 64 * 1024 * 1024


class _RedisLike:
    def pubsub(self) -> Any: ...


def _empty_overlay_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "defect_id": pl.Series([], dtype=pl.Int32),
            "map_in_selection": pl.Series([], dtype=pl.Int32),
            "table_in_selection": pl.Series([], dtype=pl.Int32),
            "gallery_in_selection": pl.Series([], dtype=pl.Int32),
            "annotation_label": pl.Series([], dtype=pl.Utf8),
            "prediction_label": pl.Series([], dtype=pl.Utf8),
            "final_class": pl.Series([], dtype=pl.Utf8),
            "prediction_confidence": pl.Series([], dtype=pl.Float64),
        }
    )


_PERSPECTIVE_TABLE_COLUMNS = (
    "defect_id",
    "sample_id",
    "inspection_time",
    "wafer_key",
    "wafer_x",
    "wafer_y",
    "die_x",
    "die_y",
    "rough_bin",
    "class_number",
    "images",
    "test_id",
    "index_x",
    "index_y",
    "adder",
    "cluster_id",
    "size_x",
    "size_y",
    "size_d",
    "area",
    "final_bin",
    "manual_bin",
    "kill_ratio",
    "annotation_label",
    "prediction_label",
    "prediction_confidence",
    "final_class",
    "review_image_ids_json",
    "map_in_selection",
    "table_in_selection",
    "gallery_in_selection",
)

_PERSPECTIVE_COLUMN_DTYPES = {
    "defect_id": pl.Int32,
    "sample_id": pl.Utf8,
    "inspection_time": pl.Utf8,
    "wafer_key": pl.Int64,
    "wafer_x": pl.Int64,
    "wafer_y": pl.Int64,
    "die_x": pl.Int64,
    "die_y": pl.Int64,
    "rough_bin": pl.Int64,
    "class_number": pl.Int64,
    "images": pl.Int32,
    "test_id": pl.Int64,
    "index_x": pl.Int64,
    "index_y": pl.Int64,
    "adder": pl.Int64,
    "cluster_id": pl.Utf8,
    "size_x": pl.Int64,
    "size_y": pl.Int64,
    "size_d": pl.Int64,
    "area": pl.Int64,
    "final_bin": pl.Int64,
    "manual_bin": pl.Int64,
    "kill_ratio": pl.Float64,
    "annotation_label": pl.Utf8,
    "prediction_label": pl.Utf8,
    "prediction_confidence": pl.Float64,
    "final_class": pl.Utf8,
    "review_image_ids_json": pl.Utf8,
    "map_in_selection": pl.Int32,
    "table_in_selection": pl.Int32,
    "gallery_in_selection": pl.Int32,
}


def _empty_samples_df() -> pl.DataFrame:
    return _select_perspective_columns(
        _normalize_samples_df(
            pl.DataFrame({"defect_id": pl.Series([], dtype=pl.Int32)})
        )
    )


def _select_perspective_columns(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        pl.col(col).cast(dtype, strict=False)
        for col, dtype in _PERSPECTIVE_COLUMN_DTYPES.items()
    ).select(*_PERSPECTIVE_TABLE_COLUMNS)


def overlay_df_from_samples(samples_df: pl.DataFrame) -> pl.DataFrame:
    df = samples_df.with_columns(pl.col("defect_id").cast(pl.Int32, strict=False))
    exprs: list[pl.Expr] = [
        pl.lit(0).cast(pl.Int32).alias("map_in_selection"),
        pl.lit(0).cast(pl.Int32).alias("table_in_selection"),
    ]
    if "annotation_label" not in df.columns:
        exprs.append(pl.lit(None).cast(pl.Utf8).alias("annotation_label"))
    if "prediction_label" not in df.columns:
        exprs.append(pl.lit(None).cast(pl.Utf8).alias("prediction_label"))
    if "prediction_confidence" not in df.columns:
        exprs.append(pl.lit(None).cast(pl.Float64).alias("prediction_confidence"))
    df = df.with_columns(exprs)
    return df.select(
        "defect_id",
        "map_in_selection",
        "table_in_selection",
        "annotation_label",
        "prediction_label",
        "prediction_confidence",
    )


def _normalize_samples_df(df: pl.DataFrame) -> pl.DataFrame:
    exprs: list[pl.Expr] = [pl.col("defect_id").cast(pl.Int32, strict=False)]
    if "map_in_selection" not in df.columns:
        exprs.append(pl.lit(0).cast(pl.Int32).alias("map_in_selection"))
    if "table_in_selection" not in df.columns:
        exprs.append(pl.lit(0).cast(pl.Int32).alias("table_in_selection"))
    if "gallery_in_selection" not in df.columns:
        exprs.append(pl.lit(0).cast(pl.Int32).alias("gallery_in_selection"))

    if "images" not in df.columns:
        exprs.append(pl.lit(0).cast(pl.Int32).alias("images"))
    else:
        exprs.append(pl.col("images").fill_null(0).cast(pl.Int32).alias("images"))

    if "review_image_ids_json" not in df.columns:
        exprs.append(pl.lit("[]").cast(pl.Utf8).alias("review_image_ids_json"))

    for col in (
        "sample_id",
        "inspection_time",
        "wafer_key",
        "wafer_x",
        "wafer_y",
        "die_x",
        "die_y",
        "reticle_x",
        "reticle_y",
        "rough_bin",
        "class_number",
        "test_id",
        "index_x",
        "index_y",
        "adder",
        "cluster_id",
        "size_x",
        "size_y",
        "size_d",
        "area",
        "final_bin",
        "manual_bin",
        "kill_ratio",
    ):
        if col in df.columns:
            continue
        if col in {"sample_id", "inspection_time", "cluster_id"}:
            exprs.append(pl.lit(None).cast(pl.Utf8).alias(col))
        elif col == "kill_ratio":
            exprs.append(pl.lit(None).cast(pl.Float64).alias(col))
        else:
            exprs.append(pl.lit(0).cast(pl.Int64).alias(col))
    if "label" in df.columns:
        exprs.append(pl.col("label").cast(pl.Utf8).alias("annotation_label"))
    elif "annotation_label" not in df.columns:
        exprs.append(pl.lit(None).cast(pl.Utf8).alias("annotation_label"))
    if "predicted_label" in df.columns:
        exprs.append(pl.col("predicted_label").cast(pl.Utf8).alias("prediction_label"))
    elif "prediction_label" not in df.columns:
        exprs.append(pl.lit(None).cast(pl.Utf8).alias("prediction_label"))
    if "confidence" in df.columns:
        exprs.append(
            pl.col("confidence").cast(pl.Float64).alias("prediction_confidence")
        )
    elif "prediction_confidence" not in df.columns:
        exprs.append(pl.lit(None).cast(pl.Float64).alias("prediction_confidence"))
    df = df.with_columns(exprs)
    return df.with_columns(
        pl.when(
            pl.col("annotation_label").is_not_null()
            & (pl.col("annotation_label") != "")
            & (pl.col("annotation_label") != "0")
        )
        .then(pl.col("annotation_label"))
        .otherwise(pl.col("prediction_label"))
        .cast(pl.Utf8)
        .alias("final_class")
    )


async def _fetch_upstream_samples_df(
    *,
    upstream_reader: ScUpstreamReader,
    inspection_time: datetime,
    wafer_key: int,
    count: int | None = None,
) -> pl.DataFrame:
    lf = await upstream_reader.list_samples(
        inspection_time,
        wafer_key,
        offset=0,
        count=count,
    )
    df = await lf.collect_async()
    review_lf = await upstream_reader.list_review_images(inspection_time, wafer_key)
    if review_lf is None:
        raise RuntimeError("upstream returned no review-image table")
    review_df = await review_lf.collect_async()
    if not review_df.is_empty():
        missing_columns = {"defect_id", "image_id"} - set(review_df.columns)
        if missing_columns:
            raise RuntimeError(
                f"upstream review-image table missing columns: {sorted(missing_columns)}"
            )
        review_df = (
            review_df.with_columns(pl.col("defect_id").cast(pl.Int32, strict=False))
            .group_by("defect_id")
            .agg(
                pl.len().cast(pl.Int32).alias("images"),
                pl.col("image_id")
                .cast(pl.Int64)
                .implode()
                .map_elements(lambda ids: json.dumps(list(ids)), return_dtype=pl.Utf8)
                .alias("review_image_ids_json"),
            )
        )
    else:
        review_df = None
    df = df.with_columns(pl.col("defect_id").cast(pl.Int32, strict=False))

    if review_df is not None:
        if "images" in df.columns:
            df = df.drop("images")
        df = df.join(review_df, on="defect_id", how="left")
    else:
        df = df.with_columns(
            pl.lit(0).cast(pl.Int32).alias("images"),
            pl.lit("[]").cast(pl.Utf8).alias("review_image_ids_json"),
        )

    if "review_image_ids_json" not in df.columns:
        df = df.with_columns(pl.lit("[]").cast(pl.Utf8).alias("review_image_ids_json"))

    return df.with_columns(
        pl.col("images").fill_null(0).cast(pl.Int32),
        pl.col("review_image_ids_json").fill_null("[]").cast(pl.Utf8),
    )


async def _build_inspection_df(
    *,
    upstream_reader: Any,
    inspection_time: str,
    wafer_key: int,
) -> pl.DataFrame:
    insp_dt = _coerce_naive_to_upstream_tz(
        datetime.fromisoformat(inspection_time.replace("Z", "+00:00"))
    )
    inspection = await upstream_reader.get_inspection(insp_dt, wafer_key)
    if inspection is None:
        raise ValueError(f"Inspection not found: {inspection_time}/{wafer_key}")
    df = await _fetch_upstream_samples_df(
        upstream_reader=upstream_reader,
        inspection_time=insp_dt,
        wafer_key=wafer_key,
        count=inspection.defects,
    )
    return _normalize_samples_df(df)


async def _build_dataset_df(
    *,
    dataset_id: str,
    org_id: str,
    storage_factory: Any,
    upstream_reader: Any,
) -> pl.DataFrame:
    storage = await storage_factory.open(dataset_id, org_id)
    sparse_lf = cast(
        pl.LazyFrame,
        await storage.list_samples(
            return_lazyframe=True,
            with_labels=True,
            with_predictions=True,
        ),
    )
    sparse_df = await sparse_lf.collect_async()
    if "defect_id" not in sparse_df.columns:
        raise ValueError("SC dataset sparse rows must include defect_id")
    meta = (
        sparse_df.select("inspection_time", "wafer_key").drop_nulls().head(1).to_dicts()
    )
    if not meta:
        raise ValueError()
    raw_time = meta[0]["inspection_time"]
    if isinstance(raw_time, datetime):
        source_time = _coerce_naive_to_upstream_tz(raw_time)
    else:
        source_time = _coerce_naive_to_upstream_tz(
            datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
        )
    source_wafer_key = int(meta[0]["wafer_key"])
    df = await _fetch_upstream_samples_df(
        upstream_reader=upstream_reader,
        inspection_time=source_time,
        wafer_key=source_wafer_key,
        count=None,
    )
    sparse_cols = [
        col
        for col in ("defect_id", "label", "predicted_label", "confidence")
        if col in sparse_df.columns
    ]
    return _normalize_samples_df(
        df.join(
            sparse_df.select(sparse_cols).with_columns(
                pl.col("defect_id").cast(pl.Int32, strict=False)
            ),
            on="defect_id",
            how="inner",
        )
    )


def _init_tables(
    server: Server,
    samples_df: pl.DataFrame,
    *,
    table_name: str,
) -> tuple[Client, Table]:
    client = server.new_local_client()
    joined = client.table(
        _select_perspective_columns(samples_df),
        name=table_name,
        index="defect_id",
    )
    return client, joined


async def _load_initial_samples(
    *,
    websocket: WebSocket,
    joined_table: Table,
    samples_df_factory: Callable[[], Awaitable[pl.DataFrame]],
    stop_event: asyncio.Event,
    update_lock: asyncio.Lock,
    executor: ThreadPoolExecutor,
) -> None:
    try:
        samples_df = await samples_df_factory()
        _logger.info("sc perspective initial samples loaded rows=%d", len(samples_df))
        if stop_event.is_set():
            return
        async with update_lock:
            await asyncio.get_running_loop().run_in_executor(
                executor,
                joined_table.update,
                _select_perspective_columns(samples_df),
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        _logger.exception("sc perspective initial samples load failed")
        if not stop_event.is_set():
            try:
                await websocket.close(code=1011)
            except Exception:
                pass


async def _redis_listener(
    *,
    redis_client: Any | None,
    dataset_id: str | None,
    joined_table: Table,
    refresh_dataset_overlay: Callable[[], Awaitable[pl.DataFrame | None]],
    stop_event: asyncio.Event,
    update_lock: asyncio.Lock,
    executor: ThreadPoolExecutor,
) -> None:
    if redis_client is None:
        await stop_event.wait()
        return
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(ANNOTATION_CHANNEL, PREDICTION_CHANNEL)
    try:
        while not stop_event.is_set():
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=0.5
            )
            if not message:
                continue
            raw = message.get("data")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            data = payload.get("data") if isinstance(payload, dict) else None
            if (
                dataset_id
                and isinstance(data, dict)
                and data.get("dataset_id") != dataset_id
            ):
                continue
            df = await refresh_dataset_overlay()
            if stop_event.is_set():
                return
            if df is not None and len(df) > 0:
                async with update_lock:
                    await asyncio.get_running_loop().run_in_executor(
                        executor,
                        joined_table.update,
                        df,
                    )
    finally:
        try:
            await pubsub.unsubscribe(ANNOTATION_CHANNEL, PREDICTION_CHANNEL)
            await pubsub.close()
        except Exception:
            pass


async def run_sc_perspective_ws(
    *,
    server: Server,
    table_name: str,
    websocket: WebSocket,
    dataset_id: str | None,
    samples_df_factory: Callable[[], Awaitable[pl.DataFrame]],
    redis_client: Any | None,
    refresh_overlay: Callable[[], Awaitable[pl.DataFrame | None]] | None = None,
) -> None:
    executor = ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="sc-perspective-handler",
    )
    update_lock = asyncio.Lock()
    local_client: Client | None = None
    joined: Table | None = None
    initial_load_task: asyncio.Task[None] | None = None
    listener_task: asyncio.Task[None] | None = None
    stop_event = asyncio.Event()

    async def _noop_overlay() -> pl.DataFrame | None:
        return None

    try:
        local_client, joined = _init_tables(
            server,
            _empty_samples_df(),
            table_name=table_name,
        )
        initial_load_task = asyncio.create_task(
            _load_initial_samples(
                websocket=websocket,
                joined_table=joined,
                samples_df_factory=samples_df_factory,
                stop_event=stop_event,
                update_lock=update_lock,
                executor=executor,
            )
        )
        listener_task = asyncio.create_task(
            _redis_listener(
                redis_client=redis_client,
                dataset_id=dataset_id,
                joined_table=joined,
                refresh_dataset_overlay=refresh_overlay or _noop_overlay,
                stop_event=stop_event,
                update_lock=update_lock,
                executor=executor,
            )
        )
        try:
            await _run_serialized_perspective_handler(
                server=server,
                websocket=websocket,
                executor=executor,
            )
        finally:
            stop_event.set()
            for task in (initial_load_task, listener_task):
                if task is None:
                    continue
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    finally:
        if joined is not None:
            try:
                await asyncio.get_running_loop().run_in_executor(
                    executor,
                    joined.delete,
                )
            except Exception:
                _logger.exception("sc perspective table cleanup failed")
        if local_client is not None:
            try:
                await asyncio.get_running_loop().run_in_executor(
                    executor,
                    local_client.terminate,
                )
            except Exception:
                _logger.exception("sc perspective local client cleanup failed")
        await asyncio.to_thread(executor.shutdown, wait=True)


async def _run_serialized_perspective_handler(
    *,
    server: Server,
    websocket: WebSocket,
    executor: ThreadPoolExecutor,
) -> None:
    """Bridge Perspective to Starlette with exactly one websocket writer.

    Perspective's bundled Starlette handler creates an independent task for every
    response. Concurrent ``send_bytes`` calls violate Starlette's websocket state
    machine under map/table load and can close the transport with code 1006.
    """

    loop = asyncio.get_running_loop()
    outgoing: asyncio.Queue[bytes | None] = asyncio.Queue(
        maxsize=_MAX_PENDING_RESPONSES
    )
    accepting_responses = True
    pending_response_bytes = 0

    def stop_overloaded_connection(message_size: int) -> None:
        nonlocal accepting_responses, pending_response_bytes
        if not accepting_responses:
            return
        accepting_responses = False
        _logger.warning(
            "sc perspective response backlog exceeded; closing websocket "
            "queued_messages=%d queued_bytes=%d next_message_bytes=%d",
            outgoing.qsize(),
            pending_response_bytes,
            message_size,
        )
        while not outgoing.empty():
            with suppress(asyncio.QueueEmpty):
                pending = outgoing.get_nowait()
                if pending is not None:
                    pending_response_bytes -= len(pending)
                outgoing.task_done()
        outgoing.put_nowait(None)

    def enqueue_on_loop(payload: bytes) -> None:
        nonlocal pending_response_bytes
        if not accepting_responses:
            return
        if (
            outgoing.full()
            or pending_response_bytes + len(payload) > _MAX_PENDING_RESPONSE_BYTES
        ):
            stop_overloaded_connection(len(payload))
            return
        pending_response_bytes += len(payload)
        outgoing.put_nowait(payload)

    def enqueue_response(message: bytes) -> None:
        if not accepting_responses:
            return
        payload = message if isinstance(message, bytes) else bytes(message)
        loop.call_soon_threadsafe(enqueue_on_loop, payload)

    session = server.new_session(enqueue_response)

    async def write_responses() -> None:
        nonlocal pending_response_bytes
        while True:
            message = await outgoing.get()
            try:
                if message is None:
                    await websocket.close(code=1013)
                    return
                pending_response_bytes -= len(message)
                await websocket.send_bytes(message)
            finally:
                outgoing.task_done()

    writer_task: asyncio.Task[None] | None = None
    try:
        await websocket.accept()
        writer_task = asyncio.create_task(
            write_responses(),
            name="sc-perspective-websocket-writer",
        )
        while True:
            receive_task = asyncio.create_task(websocket.receive())
            done, _pending = await asyncio.wait(
                (receive_task, writer_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if writer_task in done:
                receive_task.cancel()
                with suppress(asyncio.CancelledError):
                    await receive_task
                await writer_task
                return
            message = receive_task.result()
            websocket._raise_on_disconnect(message)
            payload = message.get("bytes")
            if payload is None:
                await websocket.close(code=1003)
                return
            await loop.run_in_executor(executor, session.handle_request, payload)
    except WebSocketDisconnect:
        # Normal on refresh/navigation.
        pass
    finally:
        accepting_responses = False
        await loop.run_in_executor(executor, session.close)
        if writer_task is not None:
            if not writer_task.done():
                writer_task.cancel()
            with suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                await writer_task
        while not outgoing.empty():
            with suppress(asyncio.QueueEmpty):
                outgoing.get_nowait()
                outgoing.task_done()
