from __future__ import annotations

from typing import Any, cast

SC_TRAINING_MAX_SAMPLES_PER_CLASS = 1_000


def limit_sc_training_rows_per_class(
    rows_lazyframe: Any,
    *,
    max_samples_per_class: int = SC_TRAINING_MAX_SAMPLES_PER_CLASS,
) -> Any:
    """Return deterministic labeled SC training rows capped per class."""

    if max_samples_per_class < 1:
        raise ValueError("max_samples_per_class must be at least 1")

    import polars as pl

    lazyframe = cast(pl.LazyFrame, rows_lazyframe)
    schema_names = set(lazyframe.collect_schema().names())
    label_column = (
        "label"
        if "label" in schema_names
        else "latest_label"
        if "latest_label" in schema_names
        else None
    )
    if label_column is None:
        raise ValueError("SC training rows are missing a label column")

    identity_column = next(
        (
            column
            for column in ("sample_id", "id", "defect_id")
            if column in schema_names
        ),
        None,
    )
    if identity_column is None:
        raise ValueError("SC training rows are missing a stable sample identity column")

    normalized_label = pl.col(label_column).cast(pl.Utf8).str.strip_chars()
    return (
        lazyframe.filter(pl.col(label_column).is_not_null() & (normalized_label != ""))
        .sort([label_column, identity_column])
        .group_by(label_column, maintain_order=True)
        .head(max_samples_per_class)
    )


__all__ = [
    "SC_TRAINING_MAX_SAMPLES_PER_CLASS",
    "limit_sc_training_rows_per_class",
]
