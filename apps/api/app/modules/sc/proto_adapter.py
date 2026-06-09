"""Protobuf serialization bridge for SC inspection sample endpoints."""

from __future__ import annotations

from typing import Any, Literal

import polars as pl

from proto_stubs.sc.v1 import sample_pb2

__all__ = ["make_class_list_pb", "make_wafer_map_response_pb"]


_WAFER_MAP_REQUIRED_COLUMNS = frozenset(
    {
        "defect_id",
        "wafer_x",
        "wafer_y",
        "die_x",
        "die_y",
        "reticle_x",
        "reticle_y",
        "class_number",
        "rough_bin",
        "has_review",
    }
)


def _downsample_df(
    df: pl.DataFrame, x_col: str, y_col: str, grid_size: int
) -> pl.DataFrame:
    if grid_size <= 0 or len(df) == 0:
        return df
    return (
        df.with_columns(
            (pl.col(x_col) // grid_size).alias("_gx"),
            (pl.col(y_col) // grid_size).alias("_gy"),
        )
        .unique(subset=["_gx", "_gy"], keep="first")
        .drop(["_gx", "_gy"])
    )


def _pack_points(df: pl.DataFrame, x_col: str, y_col: str) -> list[int]:
    if len(df) == 0:
        return []
    arr = (
        df.select(
            pl.col(x_col).cast(pl.Int32),
            pl.col(y_col).cast(pl.Int32),
            pl.col("defect_id").cast(pl.Int32),
            pl.col("class_number").fill_null(-1).cast(pl.Int32),
            pl.col("rough_bin").cast(pl.Int32),
            pl.col("has_review").cast(pl.Int32),
        )
        .to_numpy()
        .flatten()
    )
    return arr.tolist()


def _populate_defect_groups(
    target: Any,
    df: pl.DataFrame,
    *,
    value_column: str,
) -> None:
    if value_column not in df.columns or len(df) == 0:
        return
    grouped = (
        df.filter(pl.col(value_column).is_not_null())
        .group_by(value_column)
        .agg(pl.col("defect_id").cast(pl.Int32).alias("defect_ids"))
    )
    for row in grouped.iter_rows(named=True):
        defect_ids = row["defect_ids"]
        item = target[str(row[value_column])]
        item.count = len(defect_ids)
        item.defect_ids.extend(defect_ids)


def make_class_list_pb(df: pl.DataFrame) -> bytes:
    """Build compact class/bin/prediction/label defect-id groups."""
    if "defect_id" not in df.columns:
        raise ValueError("make_class_list_pb: missing required column: defect_id")

    msg = sample_pb2.ClassList()
    _populate_defect_groups(msg.class_numbers, df, value_column="class_number")
    _populate_defect_groups(msg.rough_bins, df, value_column="rough_bin")
    _populate_defect_groups(msg.prediction, df, value_column="predicted_label")
    _populate_defect_groups(msg.labels, df, value_column="label")
    return msg.SerializeToString()


def make_wafer_map_response_pb(
    df: pl.DataFrame,
    *,
    wafer_key: int,
    wafer_radius_nm: int = 150_000_000,
    center_x: int = 0,
    center_y: int = 0,
    origin_x: int = 0,
    origin_y: int = 0,
    die_size_x: int = 1,
    die_size_y: int = 1,
    reticle_x_die_count: int = 10,
    reticle_y_die_count: int = 10,
    sampled: bool = False,
    target_resolution: int = 600,
    include_geometry: bool = True,
    include_reticle_points: bool = True,
    zoom_x: int | None = None,
    zoom_y: int | None = None,
    zoom_w: int | None = None,
    zoom_h: int | None = None,
    map_mode: Literal["wafer", "die", "reticle"] | None = None,
) -> bytes:
    """Build a WaferMapResponse protobuf with wafer/die/reticle point arrays.

    Accepts a polars ``DataFrame`` with pre-computed coordinate columns
    (die_x, die_y, reticle_x, reticle_y).  Each point packs 6 int32 values:
    ``[x, y, defect_id, class_number, rough_bin, has_review]``.

    When *sampled* is True, each map type is independently grid-downsampled
    before packing.  *total* always reports the full defect count so the
    consumer can decide whether to request full data.
    """
    missing = _WAFER_MAP_REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"make_wafer_map_response_pb: missing required columns: {sorted(missing)}"
        )

    original_total = len(df)

    # ── Zoom filtering ─────────────────────────────────────────────────
    if zoom_x is not None and zoom_w is not None:
        zoom_x_int = int(zoom_x)
        zoom_y_int = int(zoom_y) if zoom_y is not None else 0
        zoom_w_int = int(zoom_w)
        zoom_h_int = int(zoom_h) if zoom_h is not None else 0
        coordinate_prefix = map_mode or "wafer"
        df = df.filter(
            (pl.col(f"{coordinate_prefix}_x") >= zoom_x_int)
            & (pl.col(f"{coordinate_prefix}_x") <= zoom_x_int + zoom_w_int)
            & (pl.col(f"{coordinate_prefix}_y") >= zoom_y_int)
            & (pl.col(f"{coordinate_prefix}_y") <= zoom_y_int + zoom_h_int)
        )

    # ── Protobuf message setup ─────────────────────────────────────────
    msg = sample_pb2.WaferMapResponse()
    msg.total = original_total
    msg.wafer_key = wafer_key

    if include_geometry:
        geo = msg.geometry
        geo.wafer_radius_nm = wafer_radius_nm
        geo.center_x = center_x
        geo.center_y = center_y
        geo.origin_x = origin_x
        geo.origin_y = origin_y
        geo.die_size_x = die_size_x
        geo.die_size_y = die_size_y

    msg.reticle_x_die_count = reticle_x_die_count
    msg.reticle_y_die_count = reticle_y_die_count

    n = len(df)

    # ── Downsample per map type ────────────────────────────────────────
    if sampled and n > 0:
        max_reticle_x = max(1, reticle_x_die_count * die_size_x)
        max_reticle_y = max(1, reticle_y_die_count * die_size_y)
        wafer_cell = max(1, (2 * wafer_radius_nm) // target_resolution)
        die_cell = max(1, max(die_size_x, die_size_y) // target_resolution)
        reticle_cell = max(1, max(max_reticle_x, max_reticle_y) // target_resolution)

        wafer_df = _downsample_df(df, "wafer_x", "wafer_y", wafer_cell)
        die_df = _downsample_df(df, "die_x", "die_y", die_cell)
        reticle_df = _downsample_df(df, "reticle_x", "reticle_y", reticle_cell)
        msg.is_sampled = True
    else:
        wafer_df = die_df = reticle_df = df

    # ── Pack points ────────────────────────────────────────────────────
    if map_mode in (None, "wafer"):
        msg.wafer_points.extend(_pack_points(wafer_df, "wafer_x", "wafer_y"))
    if map_mode in (None, "die"):
        msg.die_points.extend(_pack_points(die_df, "die_x", "die_y"))
    if include_reticle_points and map_mode in (None, "reticle"):
        msg.reticle_points.extend(_pack_points(reticle_df, "reticle_x", "reticle_y"))

    return msg.SerializeToString()
