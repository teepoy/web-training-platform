from __future__ import annotations

from typing import cast

import pytest

from app.modules.storage.domain.data_plane import (
    DataPlaneAuth,
    DataPlaneManifest,
    DataPlaneSchemaRegistry,
    DataPlaneShard,
    FlightEndpoint,
    validate_manifest_against_schema,
)


def test_default_schema_registry_exposes_arrow_schema_refs() -> None:
    registry = DataPlaneSchemaRegistry.default()

    schema = registry.get("sc.patch_image.v1", "1")

    assert registry.schema_ref("sc.patch_image.v1", "1") == (
        "arrow-schema://sc.patch_image.v1/1"
    )
    assert schema.field("sample_id").nullable is False
    assert schema.field("test_id").nullable is True
    assert str(schema.field("patch_defective_bytes").type) == "binary"


def test_manifest_serializes_arrow_columns_without_row_payloads() -> None:
    registry = DataPlaneSchemaRegistry.default()
    schema = registry.get("sc.patch_image.v1", "1")

    manifest = DataPlaneManifest.from_schema(
        view_contract="sc.patch_image.v1",
        view_schema_version="1",
        dataset_id="dataset-1",
        job_id="job-1",
        format="parquet",
        schema=schema,
        schema_ref=registry.schema_ref("sc.patch_image.v1", "1"),
        image_encoding="embedded_bytes",
        image_roles=("patch_template", "patch_defective"),
        label_columns=("label",),
        shards=(
            DataPlaneShard(
                uri="s3://bucket/jobs/job-1/input/shard-000.parquet",
                format="parquet",
                row_count=4096,
                size_bytes=123,
            ),
        ),
        row_count=4096,
        auth=DataPlaneAuth(mode="job_scoped", audience="runtime-service"),
        ttl_seconds=86400,
    )

    manifest.validate_transport()
    payload = manifest.to_transport_dict()

    assert payload["manifest_schema_version"] == "data-plane-manifest.v1"
    assert payload["schema_ref"] == "arrow-schema://sc.patch_image.v1/1"
    assert payload["image_roles"] == ["patch_template", "patch_defective"]
    assert payload["label_columns"] == ["label"]
    assert "rows" not in payload
    columns = cast(list[dict[str, object]], payload["columns"])
    assert columns[0] == {
        "name": "sample_id",
        "arrow_type": "string",
        "nullable": False,
    }
    validate_manifest_against_schema(manifest, registry)


def test_arrow_flight_manifest_uses_stream_endpoint_without_shards() -> None:
    registry = DataPlaneSchemaRegistry.default()
    schema = registry.get("sc.patch_image.v1", "1")

    manifest = DataPlaneManifest.from_schema(
        view_contract="sc.patch_image.v1",
        view_schema_version="1",
        dataset_id="dataset-1",
        job_id="job-1",
        format="arrow_flight",
        schema=schema,
        schema_ref=registry.schema_ref("sc.patch_image.v1", "1"),
        image_encoding="arrow_flight",
        flight=FlightEndpoint(
            endpoint="grpc://sc-upstream:9093",
            ticket="ticket",
            stream_schema_ref="arrow-schema://sc.patch_image.v1/1",
        ),
    )

    manifest.validate_transport()


def test_non_flight_manifest_requires_shards() -> None:
    registry = DataPlaneSchemaRegistry.default()
    schema = registry.get("sc.patch_image.v1", "1")

    manifest = DataPlaneManifest.from_schema(
        view_contract="sc.patch_image.v1",
        view_schema_version="1",
        dataset_id="dataset-1",
        job_id="job-1",
        format="parquet",
        schema=schema,
        schema_ref=registry.schema_ref("sc.patch_image.v1", "1"),
        image_encoding="embedded_bytes",
    )

    with pytest.raises(ValueError, match="requires at least one shard"):
        manifest.validate_transport()


def test_manifest_validation_rejects_wrong_schema_ref() -> None:
    registry = DataPlaneSchemaRegistry.default()
    schema = registry.get("sc.patch_image.v1", "1")

    manifest = DataPlaneManifest.from_schema(
        view_contract="sc.patch_image.v1",
        view_schema_version="1",
        dataset_id="dataset-1",
        job_id="job-1",
        format="parquet",
        schema=schema,
        schema_ref="arrow-schema://wrong/1",
        image_encoding="embedded_bytes",
        shards=(
            DataPlaneShard(
                uri="s3://bucket/jobs/job-1/input/shard-000.parquet",
                format="parquet",
                row_count=1,
            ),
        ),
    )

    with pytest.raises(ValueError, match="schema_ref does not match"):
        validate_manifest_against_schema(manifest, registry)
