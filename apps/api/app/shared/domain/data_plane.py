"""Stable data-plane manifest contracts shared by API and runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pyarrow as pa

ManifestFormat = Literal["parquet", "arrow_ipc", "arrow_flight"]
ManifestPurpose = Literal["train", "predict", "preview", "export"]
ImageEncoding = Literal["embedded_bytes", "signed_refs", "arrow_flight", "none"]

MANIFEST_SCHEMA_VERSION = "data-plane-manifest.v1"


@dataclass(frozen=True)
class ArrowColumn:
    name: str
    arrow_type: str
    nullable: bool

    @classmethod
    def from_field(cls, field: pa.Field) -> ArrowColumn:
        return cls(
            name=field.name,
            arrow_type=str(field.type),
            nullable=field.nullable,
        )


@dataclass(frozen=True)
class DataPlaneShard:
    uri: str
    format: ManifestFormat
    row_count: int
    size_bytes: int | None = None


@dataclass(frozen=True)
class FlightEndpoint:
    endpoint: str
    ticket: str
    stream_schema_ref: str


@dataclass(frozen=True)
class DataPlaneAuth:
    mode: Literal["job_scoped", "service"]
    audience: str


@dataclass(frozen=True)
class DataPlaneViewRequest:
    purpose: ManifestPurpose
    dataset_id: str
    job_id: str
    view_contract: str
    view_schema_version: str
    image_roles: tuple[str, ...] = ()
    label_columns: tuple[str, ...] = ()
    sample_ids: tuple[str, ...] = ()
    sample_filter: dict[str, object] | None = None
    preferred_format: ManifestFormat = "parquet"
    image_encoding: ImageEncoding = "embedded_bytes"


@dataclass(frozen=True)
class DataPlaneManifest:
    view_contract: str
    view_schema_version: str
    dataset_id: str
    job_id: str
    format: ManifestFormat
    schema_ref: str
    columns: tuple[ArrowColumn, ...]
    image_encoding: ImageEncoding
    image_roles: tuple[str, ...]
    label_columns: tuple[str, ...]
    shards: tuple[DataPlaneShard, ...] = ()
    row_count: int | None = None
    flight: FlightEndpoint | None = None
    auth: DataPlaneAuth | None = None
    ttl_seconds: int | None = None
    manifest_schema_version: str = MANIFEST_SCHEMA_VERSION

    @classmethod
    def from_schema(
        cls,
        *,
        view_contract: str,
        view_schema_version: str,
        dataset_id: str,
        job_id: str,
        format: ManifestFormat,
        schema: pa.Schema,
        schema_ref: str,
        image_encoding: ImageEncoding,
        image_roles: tuple[str, ...] = (),
        label_columns: tuple[str, ...] = (),
        shards: tuple[DataPlaneShard, ...] = (),
        row_count: int | None = None,
        flight: FlightEndpoint | None = None,
        auth: DataPlaneAuth | None = None,
        ttl_seconds: int | None = None,
    ) -> DataPlaneManifest:
        return cls(
            view_contract=view_contract,
            view_schema_version=view_schema_version,
            dataset_id=dataset_id,
            job_id=job_id,
            format=format,
            schema_ref=schema_ref,
            row_count=row_count,
            columns=tuple(ArrowColumn.from_field(field) for field in schema),
            image_encoding=image_encoding,
            image_roles=image_roles,
            label_columns=label_columns,
            shards=shards,
            flight=flight,
            auth=auth,
            ttl_seconds=ttl_seconds,
        )

    def validate_transport(self) -> None:
        if self.format == "arrow_flight":
            if self.flight is None:
                raise ValueError("arrow_flight manifest requires flight endpoint")
            if self.shards:
                raise ValueError("arrow_flight manifest must not include shards")
            return
        if self.flight is not None:
            raise ValueError("non-flight manifest must not include flight endpoint")
        if not self.shards:
            raise ValueError(f"{self.format} manifest requires at least one shard")

    def to_transport_dict(self) -> dict[str, object]:
        return {
            "manifest_schema_version": self.manifest_schema_version,
            "view_contract": self.view_contract,
            "view_schema_version": self.view_schema_version,
            "dataset_id": self.dataset_id,
            "job_id": self.job_id,
            "format": self.format,
            "schema_ref": self.schema_ref,
            "row_count": self.row_count,
            "columns": [
                {
                    "name": column.name,
                    "arrow_type": column.arrow_type,
                    "nullable": column.nullable,
                }
                for column in self.columns
            ],
            "image_encoding": self.image_encoding,
            "image_roles": list(self.image_roles),
            "label_columns": list(self.label_columns),
            "shards": [
                {
                    "uri": shard.uri,
                    "format": shard.format,
                    "row_count": shard.row_count,
                    "size_bytes": shard.size_bytes,
                }
                for shard in self.shards
            ],
            "flight": None
            if self.flight is None
            else {
                "endpoint": self.flight.endpoint,
                "ticket": self.flight.ticket,
                "stream_schema_ref": self.flight.stream_schema_ref,
            },
            "auth": None
            if self.auth is None
            else {
                "mode": self.auth.mode,
                "audience": self.auth.audience,
            },
            "ttl_seconds": self.ttl_seconds,
        }


__all__ = [
    "ArrowColumn",
    "DataPlaneAuth",
    "DataPlaneManifest",
    "DataPlaneShard",
    "DataPlaneViewRequest",
    "FlightEndpoint",
    "ImageEncoding",
    "MANIFEST_SCHEMA_VERSION",
    "ManifestFormat",
    "ManifestPurpose",
]
