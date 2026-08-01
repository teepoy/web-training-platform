from __future__ import annotations

from typing import Any
from urllib.parse import unquote, urlparse

import polars as pl

from app.shared.domain.data_plane import DataPlaneManifest


def materialized_lazyframe(
    materialized_dataset: Any,
    manifest: DataPlaneManifest,
) -> pl.LazyFrame:
    if manifest.view_contract != "sc.patch_image.v1":
        raise ValueError(
            "SC trainers require view contract 'sc.patch_image.v1', got "
            f"{manifest.view_contract!r}"
        )
    if manifest.view_schema_version != "1":
        raise ValueError(
            "SC trainers require view schema version '1', got "
            f"{manifest.view_schema_version!r}"
        )
    del materialized_dataset
    if manifest.format != "parquet" or len(manifest.shards) != 1:
        raise ValueError("SC trainers require exactly one Parquet shard")
    parsed = urlparse(manifest.shards[0].uri)
    if parsed.scheme != "file":
        raise ValueError("SC local trainers require a file:// Parquet shard")
    return (
        pl.scan_parquet(unquote(parsed.path))
        .with_columns(
            pl.concat_list(
                [
                    pl.struct(
                        pl.lit("patch_template").alias("role"),
                        pl.lit("patch_template").alias("image_type"),
                        pl.col("patch_template_bytes").alias("bytes"),
                    ),
                    pl.struct(
                        pl.lit("patch_defective").alias("role"),
                        pl.lit("patch_defective").alias("image_type"),
                        pl.col("patch_defective_bytes").alias("bytes"),
                    ),
                ]
            ).alias("images")
        )
        .drop(["patch_template_bytes", "patch_defective_bytes"])
    )


sc_materialized_lazyframe = materialized_lazyframe

__all__ = ["materialized_lazyframe", "sc_materialized_lazyframe"]
