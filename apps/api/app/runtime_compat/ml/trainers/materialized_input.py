from __future__ import annotations

from typing import Any

import polars as pl

from app.shared.domain.data_plane import DataPlaneManifest


def sc_materialized_lazyframe(
    materialized_dataset: Any,
    manifest: DataPlaneManifest,
) -> pl.LazyFrame:
    if manifest.view_contract != "sc.patch_image.v1":
        raise ValueError(
            "SC compatibility trainers require view contract "
            f"'sc.patch_image.v1', got {manifest.view_contract!r}"
        )
    if manifest.view_schema_version != "1":
        raise ValueError(
            "SC compatibility trainers require view schema version '1', got "
            f"{manifest.view_schema_version!r}"
        )

    rows: list[dict[str, Any]] = []
    for item in materialized_dataset:
        row = dict(item)
        row["images"] = [
            {
                "role": "patch_template",
                "image_type": "patch_template",
                "bytes": row.pop("patch_template_bytes", None),
            },
            {
                "role": "patch_defective",
                "image_type": "patch_defective",
                "bytes": row.pop("patch_defective_bytes", None),
            },
        ]
        rows.append(row)
    return pl.DataFrame(rows, infer_schema_length=None).lazy()


__all__ = ["sc_materialized_lazyframe"]
