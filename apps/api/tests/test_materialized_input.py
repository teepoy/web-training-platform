from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.runtime_compat.ml.trainers.materialized_input import (
    sc_materialized_lazyframe,
)
from app.shared.domain.data_plane import DataPlaneManifest, DataPlaneShard


def _manifest(path: str) -> DataPlaneManifest:
    schema = pa.schema(
        [
            pa.field("sample_id", pa.string()),
            pa.field("patch_template_bytes", pa.binary()),
            pa.field("patch_defective_bytes", pa.binary()),
        ]
    )
    return DataPlaneManifest.from_schema(
        view_contract="sc.patch_image.v1",
        view_schema_version="1",
        dataset_id="dataset-1",
        job_id="job-1",
        format="parquet",
        schema=schema,
        schema_ref="arrow-schema://sc.patch_image.v1/1",
        image_encoding="embedded_bytes",
        image_roles=("patch_template", "patch_defective"),
        shards=(
            DataPlaneShard(
                uri=f"file://{path}",
                format="parquet",
                row_count=1,
            ),
        ),
        row_count=1,
    )


def test_sc_materialized_lazyframe_scans_manifest_parquet(tmp_path) -> None:
    parquet_path = tmp_path / "materialized.parquet"
    pq.write_table(
        pa.table(
            {
                "sample_id": ["sample-1"],
                "patch_template_bytes": [b"template"],
                "patch_defective_bytes": [b"defective"],
            }
        ),
        parquet_path,
    )

    row = (
        sc_materialized_lazyframe(
            materialized_dataset=object(),
            manifest=_manifest(str(parquet_path)),
        )
        .collect()
        .to_dicts()[0]
    )

    assert row["sample_id"] == "sample-1"
    assert row["images"] == [
        {
            "role": "patch_template",
            "image_type": "patch_template",
            "bytes": b"template",
        },
        {
            "role": "patch_defective",
            "image_type": "patch_defective",
            "bytes": b"defective",
        },
    ]


def test_sc_materialized_lazyframe_rejects_non_file_shards(tmp_path) -> None:
    manifest = _manifest(str(tmp_path / "materialized.parquet"))
    remote_manifest = DataPlaneManifest(
        **{
            **manifest.__dict__,
            "shards": (
                DataPlaneShard(
                    uri="s3://bucket/materialized.parquet",
                    format="parquet",
                    row_count=1,
                ),
            ),
        }
    )

    with pytest.raises(ValueError, match="file://"):
        sc_materialized_lazyframe(object(), remote_manifest)
