from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from app.modules.storage.domain.storage_agg import DatasetStorageAgg
from app.modules.storage.domain.data_plane.manifest import (
    DataPlaneManifest,
    DataPlaneViewRequest,
)

if TYPE_CHECKING:
    import pyarrow as pa

    from app.modules.storage.domain.sparse import (
        DatasetPayloadStore,
        SampleLocator,
        ShardEntry,
    )


class DatasetStorageFactoryPort(Protocol):
    """Open a dataset through its configured physical storage backend."""

    async def open(
        self,
        dataset_id: str,
        org_id: str,
    ) -> DatasetStorageAgg: ...


class DataPlaneSchemaRegistryPort(Protocol):
    def get(self, view_contract: str, view_schema_version: str) -> "pa.Schema": ...

    def schema_ref(self, view_contract: str, view_schema_version: str) -> str: ...


class DataPlaneViewMaterializerPort(Protocol):
    async def materialize_view(
        self,
        request: DataPlaneViewRequest,
    ) -> DataPlaneManifest: ...


class SparseImportWriterPort(Protocol):
    async def flush_shard(
        self,
        *,
        shard_index: int,
        rows: list[dict[str, Any]],
        pyarrow_schema: pa.Schema,
        row_id_key: str = "sample_id",
    ) -> tuple[ShardEntry, dict[str, SampleLocator]]: ...


class SparseImportWriterFactoryPort(Protocol):
    def create(
        self,
        *,
        dataset_id: str,
        org_id: str,
        payload_store: DatasetPayloadStore,
    ) -> SparseImportWriterPort: ...
