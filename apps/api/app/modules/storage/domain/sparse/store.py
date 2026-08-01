"""Dataset payload shard and manifest store backed by object storage."""

from __future__ import annotations

import asyncio
import hashlib
from collections import OrderedDict
from pathlib import Path

from app.shared.domain.runtime import ArtifactStorage
from app.modules.storage.domain.sparse.models import (
    DatasetManifest,
    SampleLocator,
    ShardEntry,
    SparseIndexEntry,
)
from app.modules.storage.domain.sparse.index import SparseIndexReader


class DatasetPayloadStore:
    """Manages dataset payload shards and manifests in object storage.

    Organises storage under ``datasets/{org_id}/{dataset_id}`` so that
    an entire dataset payload (manifest + all shards) can be deleted
    deterministically by reading the manifest and removing every listed
    object — no prefix-listing dependency required.
    """

    def __init__(
        self,
        storage: ArtifactStorage,
        *,
        manifest_cache_max_bytes: int | None = None,
    ) -> None:
        self._storage = storage
        self._index_reader = SparseIndexReader()
        if manifest_cache_max_bytes is not None and manifest_cache_max_bytes < 0:
            raise ValueError("manifest_cache_max_bytes must not be negative")
        self._manifest_cache_max_bytes = manifest_cache_max_bytes or 0
        self._manifest_cache: OrderedDict[
            tuple[str, str], tuple[DatasetManifest, int]
        ] = OrderedDict()
        self._manifest_cache_bytes = 0
        self._manifest_cache_hits = 0
        self._manifest_cache_evictions = 0
        self._uri_scheme_prefix: str | None = None
        self._scheme_lock = asyncio.Lock()

    @property
    def storage(self) -> ArtifactStorage:
        return self._storage

    async def lookup_sample_locators(
        self,
        manifest: DatasetManifest,
        sample_ids: list[str] | set[str],
    ) -> dict[str, SampleLocator]:
        if manifest.manifest_version == "v3":
            if manifest.index is None:
                return {}
            return await self._index_reader.lookup_many(
                manifest.index,
                sample_ids,
                dataset_id=manifest.dataset_id,
                storage=self._storage,
            )
        return {
            sample_id: locator
            for sample_id in sample_ids
            if (locator := manifest.sample_index.get(sample_id)) is not None
        }

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

    @staticmethod
    def get_index_key(dataset_id: str, org_id: str) -> str:
        return f"datasets/{org_id}/{dataset_id}/index/sample-index.parquet"

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
        self._cache_manifest((manifest.dataset_id, org_id), manifest, len(data))
        self._remember_scheme_from_uri(uri, key)
        return uri

    async def get_manifest(self, dataset_id: str, org_id: str) -> DatasetManifest:
        """Read and parse the manifest stored under the canonical key."""
        key = (dataset_id, org_id)
        cached = self._manifest_cache.get(key)
        if cached is not None:
            self._manifest_cache.move_to_end(key)
            self._manifest_cache_hits += 1
            return cached[0]
        uri = await self._resolve_manifest_uri(dataset_id, org_id)
        raw = await self._storage.get_bytes(uri)
        manifest = DatasetManifest.model_validate_json(raw)
        self._cache_manifest(key, manifest, len(raw))
        return manifest

    def invalidate_manifest(self, dataset_id: str, org_id: str) -> None:
        cached = self._manifest_cache.pop((dataset_id, org_id), None)
        if cached is not None:
            self._manifest_cache_bytes -= cached[1]

    def manifest_cache_stats(self) -> dict[str, int]:
        return {
            "entries": len(self._manifest_cache),
            "retained_bytes": self._manifest_cache_bytes,
            "hits": self._manifest_cache_hits,
            "evictions": self._manifest_cache_evictions,
        }

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

    async def put_shard_file(
        self,
        *,
        dataset_id: str,
        org_id: str,
        shard_index: int,
        path: str,
        row_count: int,
        format: str = "parquet",
    ) -> ShardEntry:
        checksum, byte_size = await asyncio.to_thread(_hash_file, path)
        object_name = (
            f"{self.get_shard_prefix(dataset_id, org_id)}/{shard_index:06d}.{format}"
        )
        uri = await self._storage.put_file(
            object_name=object_name,
            path=path,
            content_type="application/octet-stream",
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

    async def put_index_file(
        self,
        *,
        dataset_id: str,
        org_id: str,
        path: str,
        row_count: int,
    ) -> SparseIndexEntry:
        checksum, byte_size = await asyncio.to_thread(_hash_file, path)
        object_name = self.get_index_key(dataset_id, org_id)
        uri = await self._storage.put_file(
            object_name=object_name,
            path=path,
            content_type="application/octet-stream",
        )
        self._remember_scheme_from_uri(uri, object_name)
        return SparseIndexEntry(
            uri=uri,
            row_count=row_count,
            checksum_sha256=checksum,
            byte_size=byte_size,
        )

    async def delete_object(self, uri: str) -> None:
        await self._storage.delete(uri)

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
        if manifest.index is not None:
            await self._storage.delete(manifest.index.uri)

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

    def _cache_manifest(
        self,
        key: tuple[str, str],
        manifest: DatasetManifest,
        size_bytes: int,
    ) -> None:
        previous = self._manifest_cache.pop(key, None)
        if previous is not None:
            self._manifest_cache_bytes -= previous[1]
        if (
            self._manifest_cache_max_bytes == 0
            or size_bytes > self._manifest_cache_max_bytes
        ):
            return
        self._manifest_cache[key] = (manifest, size_bytes)
        self._manifest_cache_bytes += size_bytes
        while self._manifest_cache_bytes > self._manifest_cache_max_bytes:
            _, (_, evicted_size) = self._manifest_cache.popitem(last=False)
            self._manifest_cache_bytes -= evicted_size
            self._manifest_cache_evictions += 1


def _hash_file(path: str) -> tuple[str, int]:
    digest = hashlib.sha256()
    size_bytes = 0
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            size_bytes += len(chunk)
    return digest.hexdigest(), size_bytes
