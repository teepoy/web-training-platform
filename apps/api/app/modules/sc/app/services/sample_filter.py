from __future__ import annotations

from typing import Any

import polars as pl

from app.modules.sc.schemas import ScSampleTableRowsRequest

SAMPLE_TABLE_FILTER_COLUMNS = {
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
    "prediction_confidence": "confidence",
    "final_class": "final_class",
}


def apply_sample_table_filter(
    lf: pl.LazyFrame,
    filter_params: dict | None,
) -> pl.LazyFrame:
    if not filter_params:
        return lf
    columns = set(lf.collect_schema().names())
    for field, filter_value in filter_params.items():
        column = SAMPLE_TABLE_FILTER_COLUMNS.get(field)
        if column is None or column not in columns:
            continue
        filter_type = getattr(filter_value, "filter_type", None)
        if filter_type == "set":
            values = list(getattr(filter_value, "values", []) or [])
            if not values:
                continue
            predicate = (
                pl.col(column).cast(pl.Utf8).is_in([str(value) for value in values])
                if field == "defect_id"
                else pl.col(column).is_in(values)
            )
            lf = lf.filter(predicate)
        elif (
            filter_type == "number" and getattr(filter_value, "type", None) == "inRange"
        ):
            lf = lf.filter(
                pl.col(column).is_between(
                    getattr(filter_value, "filter"),
                    getattr(filter_value, "filter_to"),
                    closed="both",
                )
            )
    return lf


def parse_and_apply_workflow_sample_filter(
    lf: pl.LazyFrame,
    raw_filter: dict[str, Any],
) -> pl.LazyFrame:
    filter_params = ScSampleTableRowsRequest.model_validate(
        {"filter": raw_filter}
    ).filter
    if not filter_params:
        raise ValueError("sample_filter must contain at least one condition")

    columns = set(lf.collect_schema().names())
    if "final_class" in filter_params:
        missing = {"label", "predicted_label"} - columns
        if missing:
            raise ValueError(
                f"sample_filter field 'final_class' requires columns: {sorted(missing)}"
            )
        lf = lf.with_columns(
            pl.when(
                pl.col("label").is_not_null()
                & (pl.col("label") != "")
                & (pl.col("label") != "0")
            )
            .then(pl.col("label"))
            .otherwise(pl.col("predicted_label"))
            .cast(pl.Utf8)
            .alias("final_class")
        )

    available_columns = set(lf.collect_schema().names())
    for field in filter_params:
        column = SAMPLE_TABLE_FILTER_COLUMNS.get(field)
        if column is None:
            raise ValueError(f"Unsupported sample_filter field: {field}")
        if column not in available_columns:
            raise ValueError(
                f"sample_filter field '{field}' requires missing column '{column}'"
            )

    return apply_sample_table_filter(lf, filter_params)


def sample_table_filter_requires_label_columns(
    filter_params: dict | None,
) -> tuple[bool, bool]:
    if not filter_params:
        return False, False
    fields = set(filter_params.keys())
    return "annotation_label" in fields, "prediction_label" in fields
