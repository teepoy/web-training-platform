"""Dataset payload shard and manifest store backed by object storage."""

from __future__ import annotations

import asyncio
import hashlib

from app.shared.domain.runtime import ArtifactStorage
from app.modules.storage.domain.sparse.models import DatasetManifest, ShardEntry


class DatasetPayloadStore:
    """Manages dataset payload shards and manifests in object storage.

    Organises storage under ``datasets/{org_id}/{dataset_id}`` so that
    an entire dataset payload (manifest + all shards) can be deleted
    deterministically by reading the manifest and removing every listed
    object — no prefix-listing dependency required.
    """

    def __init__(self, storage: ArtifactStorage) -> None:
        self._storage = storage
        self._manifest_cache: dict[tuple[str, str], DatasetManifest] = {}
        self._uri_scheme_prefix: str | None = None
        self._scheme_lock = asyncio.Lock()

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
        uri = await self._storage.put_bytes(
            object_name=key, data=data, content_type="application/json"
        )
        self._manifest_cache[(manifest.dataset_id, org_id)] = manifest
        self._remember_scheme_from_uri(uri, key)
        return uri

    async def get_manifest(self, dataset_id: str, org_id: str) -> DatasetManifest:
        """Read and parse the manifest stored under the canonical key."""
        cached = self._manifest_cache.get((dataset_id, org_id))
        if cached is not None:
            return cached
        uri = await self._resolve_manifest_uri(dataset_id, org_id)
        raw = await self._storage.get_bytes(uri)
        manifest = DatasetManifest.model_validate_json(raw)
        self._manifest_cache[(dataset_id, org_id)] = manifest
        return manifest

    def invalidate_manifest(self, dataset_id: str, org_id: str) -> None:
        self._manifest_cache.pop((dataset_id, org_id), None)

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
        self._remember_scheme_from_uri(uri, object_name)

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
        self.invalidate_manifest(dataset_id, org_id)

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _remember_scheme_from_uri(self, uri: str, object_name: str) -> None:
        # Storage backends return URIs of the form "<scheme>://<bucket>/<key>"
        # or "memory://<key>". Cache the prefix so future manifest lookups
        # don't need a put+delete probe to discover the scheme.
        if self._uri_scheme_prefix is not None:
            return
        if uri.endswith(object_name):
            self._uri_scheme_prefix = uri[: -len(object_name)]

    async def _resolve_manifest_uri(self, dataset_id: str, org_id: str) -> str:
        key = self.get_manifest_key(dataset_id, org_id)
        if self._uri_scheme_prefix is not None:
            return f"{self._uri_scheme_prefix}{key}"

        # First call: probe the backend once to learn the URI scheme,
        # then cache it. Subsequent calls skip the probe entirely.
        async with self._scheme_lock:
            if self._uri_scheme_prefix is None:
                tmp_key = f"{key}.__tmp_discovery__"
                tmp_uri = await self._storage.put_bytes(
                    object_name=tmp_key, data=b"", content_type="application/json"
                )
                await self._storage.delete(tmp_uri)
                self._remember_scheme_from_uri(tmp_uri, tmp_key)
                if self._uri_scheme_prefix is None:
                    return tmp_uri.replace(".__tmp_discovery__", "")
        assert self._uri_scheme_prefix is not None
        return f"{self._uri_scheme_prefix}{key}"
