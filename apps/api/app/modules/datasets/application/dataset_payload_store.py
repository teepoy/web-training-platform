from __future__ import annotations

import hashlib

from app.modules.datasets.domain.dataset_payload import DatasetManifest, ShardEntry
from app.shared.infrastructure.storage.base import ArtifactStorage


class DatasetPayloadStore:
    """Manages dataset payload shards and manifests in object storage.

    Organises storage under ``datasets/{org_id}/{dataset_id}`` so that
    an entire dataset payload (manifest + all shards) can be deleted
    deterministically by reading the manifest and removing every listed
    object — no prefix-listing dependency required.
    """

    def __init__(self, storage: ArtifactStorage) -> None:
        self._storage = storage

    # ------------------------------------------------------------------
    # prefix helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_dataset_prefix(dataset_id: str, org_id: str) -> str:
        return f"datasets/{org_id}/{dataset_id}"

    @staticmethod
    def get_shard_prefix(dataset_id: str, org_id: str) -> str:
        return f"datasets/{org_id}/{dataset_id}/shards"

    @staticmethod
    def get_manifest_key(dataset_id: str, org_id: str) -> str:
        return f"datasets/{org_id}/{dataset_id}/manifest.json"

    # ------------------------------------------------------------------
    # manifest
    # ------------------------------------------------------------------

    async def put_manifest(self, manifest: DatasetManifest, *, org_id: str) -> str:
        """Upload the manifest JSON and return its storage URI."""
        key = self.get_manifest_key(manifest.dataset_id, org_id)
        data = manifest.model_dump_json(indent=2).encode("utf-8")
        return await self._storage.put_bytes(
            object_name=key, data=data, content_type="application/json"
        )

    async def get_manifest(self, dataset_id: str, org_id: str) -> DatasetManifest:
        """Read and parse the manifest stored under the canonical key."""
        uri = await self._resolve_manifest_uri(dataset_id, org_id)
        raw = await self._storage.get_bytes(uri)
        return DatasetManifest.model_validate_json(raw)

    # ------------------------------------------------------------------
    # shards
    # ------------------------------------------------------------------

    async def put_shard(
        self,
        *,
        dataset_id: str,
        org_id: str,
        shard_index: int,
        data: bytes,
        row_count: int,
        format: str = "parquet",
    ) -> ShardEntry:
        """Upload a single shard and return its metadata entry."""
        checksum = hashlib.sha256(data).hexdigest()
        byte_size = len(data)

        object_name = (
            f"{self.get_shard_prefix(dataset_id, org_id)}/{shard_index:06d}.{format}"
        )

        uri = await self._storage.put_bytes(
            object_name=object_name, data=data, content_type="application/octet-stream"
        )

        return ShardEntry(
            shard_index=shard_index,
            uri=uri,
            row_count=row_count,
            format=format,
            checksum_sha256=checksum,
            byte_size=byte_size,
        )

    # ------------------------------------------------------------------
    # delete
    # ------------------------------------------------------------------

    async def delete_dataset_payload(self, dataset_id: str, org_id: str) -> None:
        """Deterministic sparse deletion driven by the manifest.

        Reads the manifest to discover every shard URI, deletes each
        shard, then deletes the manifest itself.  If no manifest exists
        the dataset payload is treated as already deleted (no-op).
        """
        try:
            manifest = await self.get_manifest(dataset_id, org_id)
        except FileNotFoundError:
            return

        for shard in manifest.shards:
            await self._storage.delete(shard.uri)

        manifest_uri = await self._resolve_manifest_uri(dataset_id, org_id)
        await self._storage.delete(manifest_uri)

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    async def _resolve_manifest_uri(self, dataset_id: str, org_id: str) -> str:
        """Return the storage URI for the manifest key.

        Uses a temporary discovery key to learn the URI scheme without
        overwriting or deleting any existing manifest data.
        """
        key = self.get_manifest_key(dataset_id, org_id)
        tmp_key = f"{key}.__tmp_discovery__"
        tmp_uri = await self._storage.put_bytes(
            object_name=tmp_key, data=b"", content_type="application/json"
        )
        await self._storage.delete(tmp_uri)
        return tmp_uri.replace(".__tmp_discovery__", "")
