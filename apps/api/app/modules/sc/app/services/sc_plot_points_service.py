from __future__ import annotations

from typing import Literal, cast

import polars as pl

from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.modules.sc.proto_adapter import make_wafer_map_response_pb
from app.shared.api.schemas import DatasetStorageMode
from app.shared.db.sql_repository import SqlRepository


class ScPlotPointsNotFoundError(Exception):
    def __init__(self, dataset_id: str) -> None:
        super().__init__(f"Dataset not found: {dataset_id}")


class ScPlotPointsRejectedError(Exception):
    pass


_REQUIRED_GEOMETRY_KEYS = frozenset(
    {
        "center_x",
        "center_y",
        "origin_x",
        "origin_y",
        "die_size_x",
        "die_size_y",
        "origin_index_x",
        "origin_index_y",
    }
)

_REQUIRED_POINT_COLUMNS = frozenset(
    {
        "defect_id",
        "wafer_x",
        "wafer_y",
        "die_x",
        "die_y",
        "rough_bin",
        "class_number",
        "images",
    }
)


def _apply_sample_filters(
    lf: pl.LazyFrame,
    **filters,
) -> pl.LazyFrame:
    columns = set(lf.collect_schema().names())
    for col, values in filters.items():
        if values and col in columns:
            lf = lf.filter(pl.col(col).is_in(values))
    return lf


def _require_int(mapping: dict, key: str) -> int:
    value = mapping[key]
    if isinstance(value, bool):
        raise ScPlotPointsRejectedError(f"geometry.{key} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ScPlotPointsRejectedError(f"geometry.{key} must be an integer") from exc


async def filter_box_defect_ids(
    lf: pl.LazyFrame,
    *,
    mode: Literal["wafer", "die", "reticle"],
    x: float,
    y: float,
    width: float,
    height: float,
) -> list[str]:
    x_column, y_column = {
        "wafer": ("wafer_x", "wafer_y"),
        "die": ("die_x", "die_y"),
        "reticle": ("reticle_x", "reticle_y"),
    }[mode]
    required = {"defect_id", x_column, y_column}
    missing = required - set(lf.collect_schema().names())
    if missing:
        raise ScPlotPointsRejectedError(
            f"box-filter requires SC shard columns: {sorted(missing)}"
        )

    result = await (
        lf.filter(
            pl.col(x_column).is_between(x, x + width, closed="both")
            & pl.col(y_column).is_between(y, y + height, closed="both")
        )
        .select("defect_id")
        .collect_async()
    )
    return [str(defect_id) for defect_id in result["defect_id"].to_list()]


class ScPlotPointsService:
    _SC_DATASET_TYPE = "image_sc"
    _PLOT_COLUMNS = [
        "defect_id",
        "wafer_x",
        "wafer_y",
        "rough_bin",
        "class_number",
        "images",
    ]

    def __init__(
        self,
        *,
        repository: SqlRepository,
        storage_factory: DatasetStorageFactory,
    ) -> None:
        self._repository = repository
        self._storage_factory = storage_factory

    async def build_plot_points_response(
        self,
        dataset_id: str,
        org_id: str,
        *,
        sampled: bool = True,
        target_resolution: int = 600,
        reticle_x_die_count: int = 3,
        reticle_y_die_count: int = 5,
        reticle_x_die_shift: int = 0,
        reticle_y_die_shift: int = 0,
        legend_group_by: str | None = None,
        class_numbers: list[int] | None = None,
        rough_bins: list[int] | None = None,
        predictions: list[str] | None = None,
        annotations: list[str] | None = None,
        test_ids: list[int] | None = None,
        adders: list[int] | None = None,
        cluster_ids: list[int] | None = None,
    ) -> bytes:
        storage = await self._storage_factory.open(dataset_id, org_id)

        dataset = await self._repository.get_dataset(dataset_id, org_id=org_id)
        if dataset is None:
            raise ScPlotPointsNotFoundError(dataset_id)
        if dataset.dataset_type != self._SC_DATASET_TYPE:
            raise ScPlotPointsRejectedError("plot-points requires an image_sc dataset")
        if dataset.storage_mode != DatasetStorageMode.FILE_SHARD_SPARSE:
            raise ScPlotPointsRejectedError(
                "plot-points requires a file_shard_sparse dataset"
            )

        lf = cast(
            pl.LazyFrame,
            await storage.list_samples(
                return_lazyframe=True,
                with_labels=(legend_group_by == "annotation" or bool(annotations)),
                with_predictions=(legend_group_by == "prediction" or bool(predictions)),
            ),
        )
        lf = _apply_sample_filters(
            lf,
            class_number=class_numbers,
            rough_bin=rough_bins,
            predicted_label=predictions,
            label=annotations,
            test_id=test_ids,
            adder=adders,
            cluster_id=cluster_ids,
        )
        df: pl.DataFrame = await lf.collect_async()

        missing_columns = _REQUIRED_POINT_COLUMNS - set(df.columns)
        if missing_columns:
            raise ScPlotPointsRejectedError(
                f"plot-points requires SC shard columns: {sorted(missing_columns)}"
            )

        geometry_raw = dataset.dataset_meta.get("geometry")
        if not isinstance(geometry_raw, dict):
            raise ScPlotPointsRejectedError("dataset_meta.geometry is required")
        missing_geometry = _REQUIRED_GEOMETRY_KEYS - set(geometry_raw)
        if missing_geometry:
            raise ScPlotPointsRejectedError(
                f"dataset_meta.geometry missing keys: {sorted(missing_geometry)}"
            )

        geometry = dict(geometry_raw)
        center_x = _require_int(geometry, "center_x")
        center_y = _require_int(geometry, "center_y")
        origin_x = _require_int(geometry, "origin_x")
        origin_y = _require_int(geometry, "origin_y")
        die_size_x = _require_int(geometry, "die_size_x")
        die_size_y = _require_int(geometry, "die_size_y")
        origin_index_x = _require_int(geometry, "origin_index_x")
        origin_index_y = _require_int(geometry, "origin_index_y")
        wafer_radius_nm = (
            _require_int(geometry, "wafer_radius_nm")
            if "wafer_radius_nm" in geometry
            else 150_000_000
        )
        if die_size_x <= 0 or die_size_y <= 0:
            raise ScPlotPointsRejectedError(
                "dataset_meta.geometry die sizes must be positive"
            )

        # reticle_x/reticle_y are frame-local coordinates over a grid of dies.
        # Do not collapse missing values to 0; derive them from wafer coords and
        # persisted geometry so bad metadata fails visibly.
        df = df.with_columns(
            (
                pl.col("die_x")
                + (
                    (
                        (pl.col("wafer_x") - origin_x) // die_size_x
                        - origin_index_x
                        + reticle_x_die_shift
                    )
                    % reticle_x_die_count
                )
                * die_size_x
            ).alias("reticle_x"),
            (
                pl.col("die_y")
                + (
                    (
                        (pl.col("wafer_y") - origin_y) // die_size_y
                        - origin_index_y
                        + reticle_y_die_shift
                    )
                    % reticle_y_die_count
                )
                * die_size_y
            ).alias("reticle_y"),
        )

        if "has_review" not in df.columns:
            df = df.with_columns(pl.lit(0).cast(pl.Int32).alias("has_review"))

        return make_wafer_map_response_pb(
            df,
            wafer_key=0,
            wafer_radius_nm=wafer_radius_nm,
            center_x=center_x,
            center_y=center_y,
            origin_x=origin_x,
            origin_y=origin_y,
            die_size_x=die_size_x,
            die_size_y=die_size_y,
            reticle_x_die_count=reticle_x_die_count,
            reticle_y_die_count=reticle_y_die_count,
            include_geometry=True,
            include_reticle_points=True,
            sampled=sampled,
            target_resolution=target_resolution,
            group_by=legend_group_by,
        )

    async def filter_dataset_box(
        self,
        dataset_id: str,
        org_id: str,
        *,
        mode: Literal["wafer", "die", "reticle"],
        x: float,
        y: float,
        width: float,
        height: float,
        reticle_x_die_count: int = 3,
        reticle_y_die_count: int = 5,
        reticle_x_die_shift: int = 0,
        reticle_y_die_shift: int = 0,
    ) -> list[str]:
        storage = await self._storage_factory.open(dataset_id, org_id)
        dataset = await self._repository.get_dataset(dataset_id, org_id=org_id)
        if dataset is None:
            raise ScPlotPointsNotFoundError(dataset_id)
        if dataset.dataset_type != self._SC_DATASET_TYPE:
            raise ScPlotPointsRejectedError("box-filter requires an image_sc dataset")
        if dataset.storage_mode != DatasetStorageMode.FILE_SHARD_SPARSE:
            raise ScPlotPointsRejectedError(
                "box-filter requires a file_shard_sparse dataset"
            )

        lf = cast(pl.LazyFrame, await storage.list_samples(return_lazyframe=True))
        if mode == "reticle":
            geometry_raw = dataset.dataset_meta.get("geometry")
            if not isinstance(geometry_raw, dict):
                raise ScPlotPointsRejectedError("dataset_meta.geometry is required")
            missing_geometry = _REQUIRED_GEOMETRY_KEYS - set(geometry_raw)
            if missing_geometry:
                raise ScPlotPointsRejectedError(
                    f"dataset_meta.geometry missing keys: {sorted(missing_geometry)}"
                )
            origin_x = _require_int(geometry_raw, "origin_x")
            origin_y = _require_int(geometry_raw, "origin_y")
            die_size_x = _require_int(geometry_raw, "die_size_x")
            die_size_y = _require_int(geometry_raw, "die_size_y")
            origin_index_x = _require_int(geometry_raw, "origin_index_x")
            origin_index_y = _require_int(geometry_raw, "origin_index_y")
            lf = lf.with_columns(
                (
                    pl.col("die_x")
                    + (
                        (
                            (pl.col("wafer_x") - origin_x) // die_size_x
                            - origin_index_x
                            + reticle_x_die_shift
                        )
                        % reticle_x_die_count
                    )
                    * die_size_x
                ).alias("reticle_x"),
                (
                    pl.col("die_y")
                    + (
                        (
                            (pl.col("wafer_y") - origin_y) // die_size_y
                            - origin_index_y
                            + reticle_y_die_shift
                        )
                        % reticle_y_die_count
                    )
                    * die_size_y
                ).alias("reticle_y"),
            )

        return await filter_box_defect_ids(
            lf,
            mode=mode,
            x=x,
            y=y,
            width=width,
            height=height,
        )
