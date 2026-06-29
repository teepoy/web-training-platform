from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from app.modules.sc.domain.models import _coerce_naive_to_upstream_tz
from typing import Any, cast

import polars as pl
from fastapi import WebSocket
from perspective import Server, Table
from perspective.handlers.starlette import PerspectiveStarletteHandler

from app.modules.sc.app.services.sc_plot_points_service import (
    _join_upstream_image_counts,
)
from app.shared.infrastructure.redis.event_publisher import (
    ANNOTATION_CHANNEL,
    PREDICTION_CHANNEL,
)

_logger = logging.getLogger(__name__)

_PERSPECTIVE_EXECUTOR = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="sc-perspective-handler",
)


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
    import logging

    logging.info(f"{df.columns = }")
    _images_is_list = "images" in df.columns and isinstance(
        df.schema["images"], pl.List
    )
    if _images_is_list:
        exprs.append(
            (pl.col("images").list.len() > 0)
            .cast(pl.Int32)
            .fill_null(0)
            .alias("images")
        )
        if "review_image_ids_json" not in df.columns:
            exprs.append(
                pl.col("images")
                .list.eval(
                    pl.element()
                    .filter(pl.element().struct.field("role") == "review")
                    .struct.field("review_image_id")
                )
                .map_elements(
                    lambda ids: json.dumps([int(x) for x in ids if x is not None]),
                    return_dtype=pl.Utf8,
                )
                .fill_null("[]")
                .alias("review_image_ids_json"),
            )
    elif "images" not in df.columns:
        exprs.append(pl.lit(0).cast(pl.Int32).alias("images"))
    else:
        exprs.append(pl.col("images").fill_null(0).cast(pl.Int32).alias("images"))

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
    if not _images_is_list and "review_image_ids_json" not in df.columns:
        exprs.append(pl.lit("[]").cast(pl.Utf8).alias("review_image_ids_json"))
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


async def _build_inspection_df(
    *,
    upstream_reader: Any,
    inspection_time: str,
    wafer_key: int,
    reticle_x_die_count: int,
    reticle_y_die_count: int,
    reticle_x_die_shift: int,
    reticle_y_die_shift: int,
) -> pl.DataFrame:
    insp_dt = _coerce_naive_to_upstream_tz(
        datetime.fromisoformat(inspection_time.replace("Z", "+00:00"))
    )
    inspection = await upstream_reader.get_inspection(insp_dt, wafer_key)
    if inspection is None:
        raise ValueError(f"Inspection not found: {inspection_time}/{wafer_key}")
    lf = await upstream_reader.list_samples(
        insp_dt,
        wafer_key,
        offset=0,
        count=inspection.defects,
        reticle_size_x=reticle_x_die_count,
        reticle_size_y=reticle_y_die_count,
        reticle_offset_x=reticle_x_die_shift,
        reticle_offset_y=reticle_y_die_shift,
    )
    df = await lf.collect_async()
    review_lf = await upstream_reader.list_review_images(insp_dt, wafer_key)
    review_df = await (
        review_lf.with_columns(pl.col("defect_id").cast(pl.Int32, strict=False))
        .group_by("defect_id")
        .agg(
            pl.len().cast(pl.Int32).alias("images"),
            pl.col("image_id")
            .cast(pl.Int64)
            .implode()
            .map_elements(lambda ids: json.dumps(list(ids)), return_dtype=pl.Utf8)
            .alias("review_image_ids_json"),
        )
        .collect_async()
    )
    _df = df.with_columns(pl.col("defect_id").cast(pl.Int32, strict=False))
    if "images" in _df.columns:
        _df = _df.drop("images")
    return _normalize_samples_df(
        _df.join(review_df, on="defect_id", how="left")
    ).with_columns(
        pl.col("images").fill_null(0).cast(pl.Int32),
        pl.col("review_image_ids_json").fill_null("[]").cast(pl.Utf8),
    )


async def _build_dataset_df(
    *,
    dataset_id: str,
    org_id: str,
    storage_factory: Any,
    upstream_reader: Any,
    reticle_x_die_count: int,
    reticle_y_die_count: int,
    reticle_x_die_shift: int,
    reticle_y_die_shift: int,
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
    # if {"wafer_x", "wafer_y", "die_x", "die_y"}.issubset(set(sparse_df.columns)):
    #     return _normalize_samples_df(sparse_df)

    # if (
    #     "inspection_time" not in sparse_df.columns
    #     or "wafer_key" not in sparse_df.columns
    # ):
    #     return _normalize_samples_df(sparse_df)
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
    upstream_lf = await upstream_reader.list_samples(
        source_time,
        source_wafer_key,
        count=None,
        reticle_size_x=reticle_x_die_count,
        reticle_size_y=reticle_y_die_count,
        reticle_offset_x=reticle_x_die_shift,
        reticle_offset_y=reticle_y_die_shift,
    )
    upstream_lf = await _join_upstream_image_counts(
        upstream_lf,
        upstream_reader=upstream_reader,
        inspection_time=source_time,
        wafer_key=source_wafer_key,
    )
    upstream_df = await upstream_lf.collect_async()
    import logging

    logging.info(f"{upstream_df.columns = }")
    sparse_cols = [
        col
        for col in ("defect_id", "label", "predicted_label", "confidence")
        if col in sparse_df.columns
    ]
    return _normalize_samples_df(
        upstream_df.with_columns(pl.col("defect_id").cast(pl.Int32, strict=False)).join(
            sparse_df.select(sparse_cols).with_columns(
                pl.col("defect_id").cast(pl.Int32, strict=False)
            ),
            on="defect_id",
            how="inner",
        )
    )


def _init_tables(server: Server, samples_df: pl.DataFrame) -> Table:
    client = server.new_local_client()
    joined = client.table(samples_df, name="joined_samples", index="defect_id")
    return joined


async def _redis_listener(
    *,
    redis_client: Any | None,
    dataset_id: str | None,
    joined_table: Table,
    refresh_dataset_overlay: Callable[[], Awaitable[pl.DataFrame | None]],
    stop_event: asyncio.Event,
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
            if df is not None and len(df) > 0:
                joined_table.update(df)
    finally:
        try:
            await pubsub.unsubscribe(ANNOTATION_CHANNEL, PREDICTION_CHANNEL)
            await pubsub.close()
        except Exception:
            pass


async def run_sc_perspective_ws(
    *,
    websocket: WebSocket,
    dataset_id: str | None,
    samples_df_factory: Callable[[], Awaitable[pl.DataFrame]],
    redis_client: Any | None,
    refresh_overlay: Callable[[], Awaitable[pl.DataFrame | None]] | None = None,
) -> None:
    server = Server()
    joined: Table | None = None
    stop_event = asyncio.Event()

    async def _noop_overlay() -> pl.DataFrame | None:
        return None

    try:
        samples_df = await samples_df_factory()
        import logging

        logging.info(f"{samples_df.get_column('images').min() = }")
        joined = _init_tables(server, samples_df)
        listener_task = asyncio.create_task(
            _redis_listener(
                redis_client=redis_client,
                dataset_id=dataset_id,
                joined_table=joined,
                refresh_dataset_overlay=refresh_overlay or _noop_overlay,
                stop_event=stop_event,
            )
        )
        handler = PerspectiveStarletteHandler(
            perspective_server=server,
            websocket=websocket,
            executor=_PERSPECTIVE_EXECUTOR,
        )
        try:
            await handler.run()
        finally:
            stop_event.set()
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass
    finally:
        if joined is not None:
            try:
                joined.delete()
            except Exception:
                pass
