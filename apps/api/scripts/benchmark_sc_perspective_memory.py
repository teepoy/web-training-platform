"""Measure SC Polars and Perspective memory in one isolated process.

Run inside the dev container so the benchmark uses the same allocator and
dependencies as the Perspective WebSocket service:

    python scripts/benchmark_sc_perspective_memory.py \
        --inspection-time 2026-07-29T04:00:00+08:00 --wafer-key 1
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import gc
import json
import time
from collections.abc import Sequence
from typing import Any

import polars as pl
from perspective import Server, Table, View

from app.core.config import load_config
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.modules.sc.port.http.perspective_ws import (
    _PERSPECTIVE_TABLE_COLUMNS,
    _build_inspection_df,
    _empty_samples_df,
    _select_perspective_columns,
)
from app.perspective_composition import (
    build_perspective_app_context,
    close_perspective_app_context,
)

MAP_COLUMNS = [
    "wafer_x",
    "wafer_y",
    "die_x",
    "die_y",
    "class_number",
    "images",
]
GALLERY_COLUMNS = [
    "defect_id",
    "annotation_label",
    "prediction_label",
    "prediction_confidence",
]


def current_rss_mb() -> float:
    with open("/proc/self/status", encoding="utf-8") as status:
        for line in status:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    raise RuntimeError("VmRSS was not found in /proc/self/status")


def release_unused_memory() -> None:
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (AttributeError, OSError):
        pass


def report(
    stage: str,
    *,
    started_at: float,
    frame: pl.DataFrame | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "stage": stage,
        "rss_mb": round(current_rss_mb(), 1),
        "elapsed_s": round(time.perf_counter() - started_at, 3),
    }
    if frame is not None:
        payload.update(
            {
                "rows": frame.height,
                "columns": frame.width,
                "polars_estimated_mb": round(frame.estimated_size("mb"), 1),
            }
        )
    if extra:
        payload.update(extra)
    print(json.dumps(payload, sort_keys=True), flush=True)


def materialize_view(
    table: Table,
    *,
    columns: Sequence[str],
    **config: Any,
) -> View:
    view = table.view(columns=list(columns), **config)
    view.num_rows()
    return view


async def benchmark(inspection_time: str, wafer_key: int, *, polars_only: bool) -> None:
    started_at = time.perf_counter()
    cfg = load_config()
    ctx = build_perspective_app_context(cfg)
    views: list[View] = []
    local_client = None
    table = None
    try:
        upstream_reader = ctx.injector.get(ScUpstreamReader)
        release_unused_memory()
        baseline_rss = current_rss_mb()
        report("baseline", started_at=started_at)

        samples_df = await _build_inspection_df(
            upstream_reader=upstream_reader,
            inspection_time=inspection_time,
            wafer_key=wafer_key,
        )
        report(
            "polars_inspection_frame",
            started_at=started_at,
            frame=samples_df,
            extra={"rss_delta_mb": round(current_rss_mb() - baseline_rss, 1)},
        )

        polars_result = (
            samples_df.filter(pl.col("class_number") == 1)
            .select(MAP_COLUMNS)
            .sort("die_x")
        )
        report(
            "polars_filter_select_sort",
            started_at=started_at,
            frame=polars_result,
            extra={"source_frame_retained": True},
        )
        del polars_result
        release_unused_memory()

        perspective_input = _select_perspective_columns(samples_df)
        report(
            "perspective_input_frame", started_at=started_at, frame=perspective_input
        )
        del samples_df
        release_unused_memory()
        report(
            "polars_perspective_input_only",
            started_at=started_at,
            frame=perspective_input,
            extra={"rss_delta_mb": round(current_rss_mb() - baseline_rss, 1)},
        )
        if polars_only:
            del perspective_input
            return

        server = Server()
        local_client = server.new_local_client()
        table = local_client.table(
            _empty_samples_df(),
            name="sc_memory_benchmark",
            index="defect_id",
        )
        report("perspective_empty_table", started_at=started_at)

        table.update(perspective_input)
        report(
            "perspective_table_plus_polars",
            started_at=started_at,
            frame=perspective_input,
            extra={"rss_delta_mb": round(current_rss_mb() - baseline_rss, 1)},
        )

        del perspective_input
        release_unused_memory()
        report(
            "perspective_table_only",
            started_at=started_at,
            extra={"rss_delta_mb": round(current_rss_mb() - baseline_rss, 1)},
        )

        map_view = materialize_view(table, columns=MAP_COLUMNS)
        views.append(map_view)
        report("perspective_map_view", started_at=started_at)

        map_arrow = map_view.to_arrow()
        report(
            "perspective_map_arrow",
            started_at=started_at,
            extra={"arrow_mb": round(len(map_arrow) / 1024 / 1024, 1)},
        )
        del map_arrow
        release_unused_memory()
        report("perspective_map_arrow_released", started_at=started_at)

        histogram_view = materialize_view(
            table,
            columns=["class_number"],
            group_by=["class_number"],
            aggregates={"class_number": "count"},
        )
        views.append(histogram_view)
        report("perspective_histogram_view", started_at=started_at)

        gallery_view = materialize_view(
            table,
            columns=GALLERY_COLUMNS,
            sort=[["defect_id", "asc"]],
        )
        views.append(gallery_view)
        report("perspective_gallery_view", started_at=started_at)

        sample_table_view = materialize_view(
            table,
            columns=_PERSPECTIVE_TABLE_COLUMNS,
            sort=[["defect_id", "asc"]],
        )
        views.append(sample_table_view)
        report("perspective_sample_table_view", started_at=started_at)
    finally:
        for view in reversed(views):
            view.delete()
        if table is not None:
            table.delete()
        if local_client is not None:
            local_client.terminate()
        await close_perspective_app_context(ctx)
        release_unused_memory()
        report("cleanup", started_at=started_at)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspection-time", required=True)
    parser.add_argument("--wafer-key", type=int, required=True)
    parser.add_argument("--polars-only", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        benchmark(
            args.inspection_time,
            args.wafer_key,
            polars_only=args.polars_only,
        )
    )


if __name__ == "__main__":
    main()
