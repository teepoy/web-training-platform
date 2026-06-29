from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, cast

import polars as pl

from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.modules.sc.domain.models import _coerce_naive_to_upstream_tz
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

_SAMPLE_TABLE_FILTER_COLUMNS = {
    "defect_id": "defect_id",
    "rough_bin": "rough_bin",
    "class_number": "class_number",
    "images": "images",
    "test_id": "test_id",
    "wafer_x": "wafer_x",
    "wafer_y": "wafer_y",
    "index_x": "index_x",
    "index_y": "index_y",
    "die_x": "die_x",
    "die_y": "die_y",
    "reticle_x": "reticle_x",
    "reticle_y": "reticle_y",
    "size_x": "size_x",
    "size_y": "size_y",
    "size_d": "size_d",
    "area": "area",
    "final_bin": "final_bin",
    "manual_bin": "manual_bin",
    "adder": "adder",
    "cluster_id": "cluster",
    "kill_ratio": "kill_ratio",
    "annotation_label": "label",
    "prediction_label": "predicted_label",
}

_SAMPLE_TABLE_OUTPUT_COLUMNS = frozenset(
    {
        "defect_id",
        "rough_bin",
        "class_number",
        "images",
        "test_id",
        "wafer_x",
        "wafer_y",
        "index_x",
        "index_y",
        "die_x",
        "die_y",
        "reticle_x",
        "reticle_y",
        "size_x",
        "size_y",
        "size_d",
        "area",
        "final_bin",
        "manual_bin",
        "adder",
        "cluster",
        "kill_ratio",
    }
)

_SAMPLE_TABLE_UPSTREAM_COLUMNS = frozenset(
    {
        "defect_id",
        "rough_bin",
        "class_number",
        "test_id",
        "wafer_x",
        "wafer_y",
        "index_x",
        "index_y",
        "die_x",
        "die_y",
        "reticle_x",
        "reticle_y",
        "size_x",
        "size_y",
        "size_d",
        "area",
        "final_bin",
        "manual_bin",
        "adder",
        "cluster",
        "kill_ratio",
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


def apply_sample_table_filter(
    lf: pl.LazyFrame,
    filter_params: dict | None,
) -> pl.LazyFrame:
    if not filter_params:
        return lf
    columns = set(lf.collect_schema().names())
    for field, filter_value in filter_params.items():
        col = _SAMPLE_TABLE_FILTER_COLUMNS.get(field)
        if col is None or col not in columns:
            continue
        filter_type = getattr(filter_value, "filter_type", None)
        if filter_type == "set":
            values = list(getattr(filter_value, "values", []) or [])
            if not values:
                continue
            predicate = (
                pl.col(col).cast(pl.Utf8).is_in([str(value) for value in values])
                if field == "defect_id"
                else pl.col(col).is_in(values)
            )
            lf = lf.filter(predicate)
        elif (
            filter_type == "number" and getattr(filter_value, "type", None) == "inRange"
        ):
            lf = lf.filter(
                pl.col(col).is_between(
                    getattr(filter_value, "filter"),
                    getattr(filter_value, "filter_to"),
                    closed="both",
                )
            )
    return lf


def sample_table_filter_requires_label_columns(
    filter_params: dict | None,
) -> tuple[bool, bool]:
    if not filter_params:
        return False, False
    fields = set(filter_params.keys())
    return "annotation_label" in fields, "prediction_label" in fields


def _parse_dataset_source_inspection_time(raw: Any) -> datetime:
    if not isinstance(raw, str) or not raw.strip():
        raise ScPlotPointsRejectedError(
            "dataset_meta.source_inspection_time is required"
        )
    try:
        dt = datetime.fromisoformat(raw)
        return _coerce_naive_to_upstream_tz(dt)
    except ValueError as exc:
        raise ScPlotPointsRejectedError(
            f"Invalid dataset_meta.source_inspection_time: {raw!r}"
        ) from exc


async def _dataset_source_identity(
    dataset_meta: dict[str, Any],
    sparse_lf: pl.LazyFrame,
) -> tuple[datetime, int]:
    source_time = dataset_meta.get("source_inspection_time")
    source_wafer_key = dataset_meta.get("source_wafer_key")
    if source_time is not None and source_wafer_key is not None:
        return _parse_dataset_source_inspection_time(source_time), int(source_wafer_key)

    columns = set(sparse_lf.collect_schema().names())
    missing = {"inspection_time", "wafer_key"} - columns
    if missing:
        raise ScPlotPointsRejectedError(
            "sample-table requires dataset source identity in dataset_meta "
            f"or sparse shard columns: {sorted(missing)}"
        )
    source_df = (
        await sparse_lf.select("inspection_time", "wafer_key").limit(1).collect_async()
    )
    if len(source_df) == 0:
        raise ScPlotPointsRejectedError("sample-table requires a non-empty SC dataset")
    return _parse_dataset_source_inspection_time(source_df["inspection_time"][0]), int(
        source_df["wafer_key"][0]
    )


def _apply_sample_table_sort(
    lf: pl.LazyFrame,
    sort_params: Any | None,
    requested: list[str] | None,
) -> pl.LazyFrame:
    if sort_params is not None:
        field = getattr(sort_params, "field", "")
        direction = getattr(sort_params, "direction", None)
        column = _SAMPLE_TABLE_FILTER_COLUMNS.get(field)
        if column is not None and column in lf.collect_schema().names() and direction:
            if field == "defect_id":
                return lf.sort(
                    pl.col(column).cast(pl.Int64), descending=(direction == "desc")
                )
            return lf.sort(column, descending=(direction == "desc"))
    if requested is not None:
        request_order = {defect_id: index for index, defect_id in enumerate(requested)}
        return (
            lf.with_columns(
                pl.col("defect_id")
                .cast(pl.Utf8)
                .replace_strict(request_order, default=len(request_order))
                .alias("_request_order")
            )
            .sort("_request_order")
            .drop("_request_order")
        )
    return (
        lf.sort(pl.col("defect_id").cast(pl.Int64))
        if "defect_id" in lf.collect_schema().names()
        else lf
    )


def _int_value(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if value is None:
        return 0
    if isinstance(value, float) and value != value:
        return 0
    return int(value)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and value != value:
        return None
    return float(value)


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def encode_defect_ids_int32le(defect_ids: list[int]) -> bytes:
    return b"".join(
        int(defect_id).to_bytes(4, byteorder="little", signed=True)
        for defect_id in defect_ids
    )


async def sorted_defect_ids_from_lazyframe(lf: pl.LazyFrame) -> list[int]:
    if "defect_id" not in lf.collect_schema().names():
        raise ScPlotPointsRejectedError("defect ids require a defect_id column")

    df = await (
        lf.select(pl.col("defect_id").cast(pl.Int64).alias("defect_id"))
        .drop_nulls()
        .unique()
        .sort("defect_id")
        .collect_async()
    )
    defect_ids = [int(value) for value in df["defect_id"].to_list()]
    for defect_id in defect_ids:
        if defect_id < -(2**31) or defect_id > 2**31 - 1:
            raise ScPlotPointsRejectedError(
                f"defect_id out of Int32 range: {defect_id}"
            )
    return defect_ids


async def _join_upstream_image_counts(
    lf: pl.LazyFrame,
    *,
    upstream_reader: Any,
    inspection_time: datetime,
    wafer_key: int,
) -> pl.LazyFrame:
    review_lf = await upstream_reader.list_review_images(inspection_time, wafer_key)
    image_counts_lf = (
        review_lf.with_columns(pl.col("defect_id").cast(pl.Utf8))
        .group_by("defect_id")
        .agg(pl.lit(1).cast(pl.Int32).alias("images"))
    )
    if "images" in lf.collect_schema().names():
        lf = lf.drop("images")
    return (
        lf.with_columns(pl.col("defect_id").cast(pl.Utf8))
        .join(image_counts_lf, on="defect_id", how="left")
        .with_columns(pl.col("images").fill_null(0).cast(pl.Int32))
    )


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

    async def ensure_plot_points_allowed(self, dataset_id: str, org_id: str) -> None:
        dataset = await self._repository.get_dataset(dataset_id, org_id=org_id)
        if dataset is None:
            raise ScPlotPointsNotFoundError(dataset_id)
        if dataset.dataset_type != self._SC_DATASET_TYPE:
            raise ScPlotPointsRejectedError("plot-points requires an image_sc dataset")
        if dataset.storage_mode != DatasetStorageMode.FILE_SHARD_SPARSE:
            raise ScPlotPointsRejectedError(
                "plot-points requires a file_shard_sparse dataset"
            )

    async def build_plot_points_response(
        self,
        dataset_id: str,
        org_id: str,
        *,
        upstream_reader: Any,
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
        filter_params: dict | None = None,
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

        filter_needs_labels, filter_needs_predictions = (
            sample_table_filter_requires_label_columns(filter_params)
        )
        lf = cast(
            pl.LazyFrame,
            await storage.list_samples(
                return_lazyframe=True,
                with_labels=(
                    legend_group_by == "annotation"
                    or bool(annotations)
                    or filter_needs_labels
                ),
                with_predictions=(
                    legend_group_by == "prediction"
                    or bool(predictions)
                    or filter_needs_predictions
                ),
            ),
        )
        source_inspection_time, source_wafer_key = await _dataset_source_identity(
            dataset.dataset_meta, lf
        )
        lf = await _join_upstream_image_counts(
            lf,
            upstream_reader=upstream_reader,
            inspection_time=source_inspection_time,
            wafer_key=source_wafer_key,
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
        lf = apply_sample_table_filter(lf, filter_params)
        df: pl.DataFrame = await lf.collect_async()

        missing_columns = _REQUIRED_POINT_COLUMNS - set(df.columns)
        if missing_columns:
            raise ScPlotPointsRejectedError(
                f"plot-points requires SC shard columns: {sorted(missing_columns)}"
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

        df = df.with_columns((pl.col("images") > 0).cast(pl.Int32).alias("has_review"))

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
        filter_params: dict | None = None,
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

        filter_needs_labels, filter_needs_predictions = (
            sample_table_filter_requires_label_columns(filter_params)
        )
        lf = cast(
            pl.LazyFrame,
            await storage.list_samples(
                return_lazyframe=True,
                with_labels=filter_needs_labels,
                with_predictions=filter_needs_predictions,
            ),
        )
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

        lf = apply_sample_table_filter(lf, filter_params)

        return await filter_box_defect_ids(
            lf,
            mode=mode,
            x=x,
            y=y,
            width=width,
            height=height,
        )

    async def build_dataset_sample_table_rows(
        self,
        dataset_id: str,
        org_id: str,
        *,
        upstream_reader: Any,
        defect_ids: list[str],
        anchor: str | None,
        page: int,
        page_size: int,
        limit: int,
        filter_params: dict | None,
        sort_params: Any | None,
        reticle_x_die_count: int,
        reticle_y_die_count: int,
        reticle_x_die_shift: int,
        reticle_y_die_shift: int,
    ) -> tuple[list[dict[str, Any]], int, str | None]:
        dataset = await self._repository.get_dataset(dataset_id, org_id=org_id)
        if dataset is None:
            raise ScPlotPointsNotFoundError(dataset_id)
        if dataset.dataset_type != self._SC_DATASET_TYPE:
            raise ScPlotPointsRejectedError("sample-table requires an image_sc dataset")
        if dataset.storage_mode != DatasetStorageMode.FILE_SHARD_SPARSE:
            raise ScPlotPointsRejectedError(
                "sample-table requires a file_shard_sparse dataset"
            )

        geometry_raw = dataset.dataset_meta.get("geometry")
        if not isinstance(geometry_raw, dict):
            raise ScPlotPointsRejectedError("dataset_meta.geometry is required")
        missing_geometry = _REQUIRED_GEOMETRY_KEYS - set(geometry_raw)
        if missing_geometry:
            raise ScPlotPointsRejectedError(
                f"dataset_meta.geometry missing keys: {sorted(missing_geometry)}"
            )
        origin_index_x = _require_int(geometry_raw, "origin_index_x")
        origin_index_y = _require_int(geometry_raw, "origin_index_y")

        storage = await self._storage_factory.open(dataset_id, org_id)
        sparse_lf = cast(
            pl.LazyFrame,
            await storage.list_samples(
                return_lazyframe=True,
                with_labels=True,
                with_predictions=True,
            ),
        )
        source_inspection_time, source_wafer_key = await _dataset_source_identity(
            dataset.dataset_meta, sparse_lf
        )
        upstream_lf = await upstream_reader.list_samples(
            source_inspection_time,
            source_wafer_key,
            count=None,
            reticle_size_x=reticle_x_die_count,
            reticle_size_y=reticle_y_die_count,
            reticle_offset_x=reticle_x_die_shift - origin_index_x,
            reticle_offset_y=reticle_y_die_shift - origin_index_y,
        )

        upstream_missing = _SAMPLE_TABLE_UPSTREAM_COLUMNS - set(
            upstream_lf.collect_schema().names()
        )
        if upstream_missing:
            raise ScPlotPointsRejectedError(
                f"sample-table requires SC upstream columns: {sorted(upstream_missing)}"
            )

        sparse_columns = set(sparse_lf.collect_schema().names())
        sparse_select_columns = ["defect_id"]
        for column in ("label", "predicted_label", "confidence"):
            if column in sparse_columns:
                sparse_select_columns.append(column)
        sparse_lf = sparse_lf.select(sparse_select_columns).with_columns(
            pl.col("defect_id").cast(pl.Utf8)
        )

        lf = upstream_lf.with_columns(pl.col("defect_id").cast(pl.Utf8)).join(
            sparse_lf,
            on="defect_id",
            how="inner",
        )
        lf = await _join_upstream_image_counts(
            lf,
            upstream_reader=upstream_reader,
            inspection_time=source_inspection_time,
            wafer_key=source_wafer_key,
        )

        missing = _SAMPLE_TABLE_OUTPUT_COLUMNS - set(lf.collect_schema().names())
        if missing:
            raise ScPlotPointsRejectedError(
                f"sample-table requires SC joined columns: {sorted(missing)}"
            )

        requested = list(dict.fromkeys(defect_ids)) if defect_ids else None
        if requested is not None:
            lf = lf.filter(pl.col("defect_id").cast(pl.Utf8).is_in(set(requested)))
        lf = apply_sample_table_filter(lf, filter_params)
        lf = _apply_sample_table_sort(lf, sort_params, requested)

        offset = int(anchor) if anchor and anchor.isdigit() else page * page_size
        page_limit = limit if anchor is not None else page_size
        total_df = await lf.select(pl.len().alias("total")).collect_async()
        page_df = await lf.slice(offset, page_limit).collect_async()
        total = int(total_df["total"][0]) if len(total_df) else 0
        rows: list[dict[str, Any]] = []
        for row in page_df.to_dicts():
            rows.append(
                {
                    "defect_id": str(row["defect_id"]),
                    "rough_bin": _int_value(row, "rough_bin"),
                    "class_number": _int_value(row, "class_number"),
                    "images": _int_value(row, "images"),
                    "test_id": _int_value(row, "test_id"),
                    "wafer_x": _int_value(row, "wafer_x"),
                    "wafer_y": _int_value(row, "wafer_y"),
                    "index_x": _int_value(row, "index_x"),
                    "index_y": _int_value(row, "index_y"),
                    "adder": _int_value(row, "adder"),
                    "cluster_id": None
                    if row.get("cluster") is None
                    else _int_value(row, "cluster"),
                    "die_x": _int_value(row, "die_x"),
                    "die_y": _int_value(row, "die_y"),
                    "reticle_x": _int_value(row, "reticle_x"),
                    "reticle_y": _int_value(row, "reticle_y"),
                    "size_x": _int_value(row, "size_x"),
                    "size_y": _int_value(row, "size_y"),
                    "size_d": _int_value(row, "size_d"),
                    "area": _int_value(row, "area"),
                    "final_bin": _int_value(row, "final_bin"),
                    "manual_bin": _int_value(row, "manual_bin"),
                    "kill_ratio": _float_or_none(row.get("kill_ratio")),
                    "annotation_label": _str_or_none(row.get("label")),
                    "prediction_label": _str_or_none(row.get("predicted_label")),
                    "prediction_confidence": _float_or_none(row.get("confidence")),
                }
            )
        next_offset = offset + len(rows)
        next_anchor = str(next_offset) if next_offset < total else None
        return rows, total, next_anchor

    async def build_defect_ids_response(self, dataset_id: str, org_id: str) -> bytes:
        dataset = await self._repository.get_dataset(dataset_id, org_id=org_id)
        if dataset is None:
            raise ScPlotPointsNotFoundError(dataset_id)
        if dataset.dataset_type != self._SC_DATASET_TYPE:
            raise ScPlotPointsRejectedError("defect ids require an image_sc dataset")
        if dataset.storage_mode != DatasetStorageMode.FILE_SHARD_SPARSE:
            raise ScPlotPointsRejectedError(
                "defect ids require a file_shard_sparse dataset"
            )

        storage = await self._storage_factory.open(dataset_id, org_id)
        lf = cast(pl.LazyFrame, await storage.list_samples(return_lazyframe=True))
        defect_ids = await sorted_defect_ids_from_lazyframe(lf)
        return encode_defect_ids_int32le(defect_ids)
