from __future__ import annotations

import pyarrow as pa

from app.shared.domain.data_plane import DataPlaneManifest, DataPlaneShard


def _manifest() -> DataPlaneManifest:
    schema = pa.schema([pa.field("sample_id", pa.string(), nullable=False)])
    return DataPlaneManifest.from_schema(
        view_contract="image.labeled.v1",
        view_schema_version="1",
        dataset_id="dataset-1",
        job_id="job-1",
        format="parquet",
        schema=schema,
        schema_ref="arrow-schema://image.labeled.v1/1",
        image_encoding="embedded_bytes",
        shards=(
            DataPlaneShard(
                uri="s3://bucket/job-1/input/shard-000.parquet",
                format="parquet",
                row_count=1,
            ),
        ),
        row_count=1,
    )


def test_data_plane_manifest_is_transport_dict_without_rows() -> None:
    payload = _manifest().to_transport_dict()

    assert payload["manifest_schema_version"] == "data-plane-manifest.v1"
    assert payload["view_contract"] == "image.labeled.v1"
    assert "rows" not in payload
