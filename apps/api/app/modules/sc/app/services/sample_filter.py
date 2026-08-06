from __future__ import annotations

from collections.abc import Iterable
from functools import reduce
from operator import and_, or_
from typing import Any

import polars as pl

from app.modules.sc.schemas import (
    ScWorkflowSampleFilter,
    ScWorkflowSampleFilterGroup,
    ScWorkflowSampleFilterItem,
)

SAMPLE_TABLE_FILTER_COLUMNS = {
    "row_key": "sample_id",
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

MISSING_FILTER_VALUES = {
    "annotation_label": "__unlabeled__",
    "prediction_label": "__no_prediction__",
    "final_class": "__unclassified__",
}


def _string_filter_value(value: object) -> str:
    """Match JSON integer IDs after Pydantic's float normalization."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def apply_sample_table_filter(
    lf: pl.LazyFrame,
    filter_params: dict | None,
) -> pl.LazyFrame:
    if not filter_params:
        return lf
    return _apply_sample_filter_items(lf, filter_params.items())


def _apply_sample_filter_items(
    lf: pl.LazyFrame,
    filter_items: Iterable[tuple[str, object]],
) -> pl.LazyFrame:
    columns = set(lf.collect_schema().names())
    for field, filter_value in filter_items:
        column = SAMPLE_TABLE_FILTER_COLUMNS.get(field)
        if column is None or column not in columns:
            continue
        filter_type = getattr(filter_value, "filter_type", None)
        if filter_type == "set":
            values = list(getattr(filter_value, "values", []) or [])
            exclude = bool(getattr(filter_value, "exclude", False))
            if not values and exclude:
                continue
            missing_value = MISSING_FILTER_VALUES.get(field)
            include_missing = missing_value is not None and missing_value in values
            concrete_values = [value for value in values if value != missing_value]
            predicate = (
                pl.col(column)
                .cast(pl.Utf8)
                .is_in([_string_filter_value(value) for value in concrete_values])
                if field in {"defect_id", "row_key"}
                else pl.col(column).is_in(concrete_values)
            )
            if include_missing:
                predicate = predicate | pl.col(column).is_null()
            predicate = predicate.fill_null(False)
            if exclude:
                predicate = ~predicate
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


def _workflow_filter_items(
    items: Iterable[ScWorkflowSampleFilterItem | ScWorkflowSampleFilterGroup],
) -> Iterable[ScWorkflowSampleFilterItem]:
    for item in items:
        if isinstance(item, ScWorkflowSampleFilterGroup):
            yield from _workflow_filter_items(item.items)
        else:
            yield item


def _workflow_condition_predicate(
    item: ScWorkflowSampleFilterItem,
) -> pl.Expr | None:
    field = item.field
    column = SAMPLE_TABLE_FILTER_COLUMNS[field]
    filter_value = item.condition
    if filter_value.filter_type == "set":
        values = list(filter_value.values)
        if not values and filter_value.exclude:
            return None
        missing_value = MISSING_FILTER_VALUES.get(field)
        include_missing = missing_value is not None and missing_value in values
        concrete_values = [value for value in values if value != missing_value]
        predicate = (
            pl.col(column)
            .cast(pl.Utf8)
            .is_in([_string_filter_value(value) for value in concrete_values])
            if field in {"defect_id", "row_key"}
            else pl.col(column).is_in(concrete_values)
        )
        if include_missing:
            predicate = predicate | pl.col(column).is_null()
        predicate = predicate.fill_null(False)
        return ~predicate if filter_value.exclude else predicate
    return pl.col(column).is_between(
        filter_value.filter,
        filter_value.filter_to,
        closed="both",
    )


def _workflow_group_predicate(
    *,
    combinator: str,
    items: Iterable[ScWorkflowSampleFilterItem | ScWorkflowSampleFilterGroup],
) -> pl.Expr | None:
    predicates: list[pl.Expr] = []
    for item in items:
        predicate = (
            _workflow_group_predicate(
                combinator=item.combinator,
                items=item.items,
            )
            if isinstance(item, ScWorkflowSampleFilterGroup)
            else _workflow_condition_predicate(item)
        )
        if predicate is not None:
            predicates.append(predicate)
    if not predicates:
        return None
    return reduce(and_ if combinator == "and" else or_, predicates)


def parse_and_apply_workflow_sample_filter(
    lf: pl.LazyFrame,
    raw_filter: dict[str, Any],
) -> pl.LazyFrame:
    sample_filter = ScWorkflowSampleFilter.model_validate(raw_filter)
    filter_items = list(_workflow_filter_items(sample_filter.items))

    columns = set(lf.collect_schema().names())
    if any(item.field == "final_class" for item in filter_items):
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
    for item in filter_items:
        field = item.field
        column = SAMPLE_TABLE_FILTER_COLUMNS.get(field)
        if column is None:
            raise ValueError(f"Unsupported sample_filter field: {field}")
        if column not in available_columns:
            raise ValueError(
                f"sample_filter field '{field}' requires missing column '{column}'"
            )

    predicate = _workflow_group_predicate(
        combinator=sample_filter.combinator,
        items=sample_filter.items,
    )
    return lf if predicate is None else lf.filter(predicate)


def sample_table_filter_requires_label_columns(
    filter_params: dict | None,
) -> tuple[bool, bool]:
    if not filter_params:
        return False, False
    fields = set(filter_params.keys())
    return "annotation_label" in fields, "prediction_label" in fields
