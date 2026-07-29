from __future__ import annotations

from app.modules.storage.domain.data_plane.manifest import (
    ArrowColumn,
    DataPlaneManifest,
)
from app.modules.storage.domain.data_plane.schemas import DataPlaneSchemaRegistry


def validate_manifest_against_schema(
    manifest: DataPlaneManifest,
    registry: DataPlaneSchemaRegistry,
) -> None:
    manifest.validate_transport()
    schema = registry.get(manifest.view_contract, manifest.view_schema_version)
    expected_schema_ref = registry.schema_ref(
        manifest.view_contract,
        manifest.view_schema_version,
    )
    if manifest.schema_ref != expected_schema_ref:
        raise ValueError(
            "Manifest schema_ref does not match registered view schema: "
            f"{manifest.schema_ref} != {expected_schema_ref}"
        )

    expected_columns = tuple(ArrowColumn.from_field(field) for field in schema)
    if manifest.columns != expected_columns:
        raise ValueError(
            "Manifest columns do not match registered Arrow schema for "
            f"{manifest.view_contract}/{manifest.view_schema_version}"
        )
