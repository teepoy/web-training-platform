from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.modules.sc.runtime.materialized_input import sc_parquet_paths_from_manifest
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


def test_sc_manifest_resolves_local_parquet_paths_in_order(tmp_path) -> None:
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

    assert sc_parquet_paths_from_manifest(_manifest(str(parquet_path))) == (
        parquet_path,
    )


def test_sc_manifest_rejects_non_file_shards(tmp_path) -> None:
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
        sc_parquet_paths_from_manifest(remote_manifest)
