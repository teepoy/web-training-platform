"""Baseline tests for DatasetPayloadStore (sparse shard/manifest store).

Tests cover manifest put/get roundtrip, shard upload with checksum,
deterministic delete, and object key prefix construction.

Uses an in-memory mock of ``ArtifactStorage`` — no compose services required.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.shared.domain.protocols import ArtifactStorage
from app.modules.storage.domain.sparse.models import DatasetManifest, ShardEntry
from app.modules.storage.domain.sparse.store import DatasetPayloadStore


# ---------------------------------------------------------------------------
# In-memory ArtifactStorage mock
# ---------------------------------------------------------------------------


class _InMemoryStore:
    """Minimal in-memory ``ArtifactStorage`` for tests.

    Stores bytes keyed by object name (last path segment of URI).
    """

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}
        self._content_types: dict[str, str] = {}

    async def put_bytes(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        self._data[object_name] = data
        self._content_types[object_name] = content_type
        return f"memory://{object_name}"

    async def get_bytes(self, uri: str) -> bytes:
        key = uri.removeprefix("memory://")
        if key not in self._data:
            raise FileNotFoundError(f"Object not found: {uri}")
        return self._data[key]

    async def put_file(
        self,
        object_name: str,
        path: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        return await self.put_bytes(
            object_name,
            Path(path).read_bytes(),
            content_type,
        )

    async def get_file(self, uri: str, destination: str) -> None:
        Path(destination).write_bytes(await self.get_bytes(uri))

    async def delete(self, uri: str) -> None:
        key = uri.removeprefix("memory://")
        self._data.pop(key, None)
        self._content_types.pop(key, None)

    async def list_prefix(self, prefix: str) -> list[str]:
        return [f"memory://{k}" for k in self._data if k.startswith(prefix)]


# Fixtures that implement the ArtifactStorage protocol
# (using a plain class avoids the complexity of runtime_checkable protocol
#  from a test helper)
pytest_plugins: list[str] = []


@pytest.fixture
def storage() -> ArtifactStorage:
    return _InMemoryStore()


@pytest.fixture
def store(storage: ArtifactStorage) -> DatasetPayloadStore:
    return DatasetPayloadStore(storage)


@pytest.fixture
def sample_manifest() -> DatasetManifest:
    return DatasetManifest(
        dataset_id="ds-test-001",
        storage_mode="file_shard_sparse",
        shard_count=2,
        total_rows=100,
        schema_columns=[],
        shards=[],
    )


# ---------------------------------------------------------------------------
# Prefix helpers
# ---------------------------------------------------------------------------


class TestPrefixHelpers:
    """Static prefix/key helper methods."""

    def test_dataset_prefix(self) -> None:
        prefix = DatasetPayloadStore.get_dataset_prefix(
            dataset_id="ds-1", org_id="org-42"
        )
        assert prefix == "datasets/org-42/ds-1"

    def test_shard_prefix(self) -> None:
        prefix = DatasetPayloadStore.get_shard_prefix(
            dataset_id="ds-1", org_id="org-42"
        )
        assert prefix == "datasets/org-42/ds-1/shards"

    def test_manifest_key(self) -> None:
        key = DatasetPayloadStore.get_manifest_key(dataset_id="ds-1", org_id="org-42")
        assert key == "datasets/org-42/ds-1/manifest.json"


# ---------------------------------------------------------------------------
# Manifest put / get roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestManifestRoundtrip:
    """Write a manifest, read it back — verify all fields survive."""

    async def test_put_and_get_manifest(
        self,
        store: DatasetPayloadStore,
        storage: ArtifactStorage,
        sample_manifest: DatasetManifest,
    ) -> None:
        uri = await store.put_manifest(sample_manifest, org_id="org-42")
        assert isinstance(uri, str)
        assert "manifest.json" in uri

        retrieved = await store.get_manifest("ds-test-001", "org-42")
        assert retrieved.dataset_id == sample_manifest.dataset_id
        assert retrieved.storage_mode == sample_manifest.storage_mode
        assert retrieved.shard_count == sample_manifest.shard_count
        assert retrieved.total_rows == sample_manifest.total_rows

    async def test_manifest_roundtrip_with_shards(
        self,
        store: DatasetPayloadStore,
        storage: ArtifactStorage,
    ) -> None:
        shards = [
            ShardEntry(
                shard_index=0,
                uri="memory://shard0.parquet",
                row_count=50,
                format="parquet",
                checksum_sha256="a" * 64,
                byte_size=1024,
            ),
            ShardEntry(
                shard_index=1,
                uri="memory://shard1.parquet",
                row_count=50,
                format="parquet",
                checksum_sha256="b" * 64,
                byte_size=2048,
            ),
        ]
        manifest = DatasetManifest(
            dataset_id="ds-shard-test",
            storage_mode="file_shard_sparse",
            shard_count=2,
            total_rows=100,
            shards=shards,
        )

        uri = await store.put_manifest(manifest, org_id="org-99")
        assert uri

        retrieved = await store.get_manifest("ds-shard-test", "org-99")
        assert len(retrieved.shards) == 2
        assert retrieved.shards[0].shard_index == 0
        assert retrieved.shards[0].row_count == 50
        assert retrieved.shards[1].shard_index == 1
        assert retrieved.shards[1].byte_size == 2048

    async def test_schema_version_roundtrip(
        self,
        store: DatasetPayloadStore,
    ) -> None:
        """``schema_version`` is populated on the manifest model — verify
        it survives put/get serialization round-trip."""
        manifest = DatasetManifest(
            dataset_id="ds-versioned",
            storage_mode="file_shard_sparse",
            shard_count=1,
            total_rows=10,
            schema_version="v2",
        )
        await store.put_manifest(manifest, org_id="org-42")
        retrieved = await store.get_manifest("ds-versioned", "org-42")
        assert retrieved.schema_version == "v2"

    async def test_manifest_without_schema_version_defaults_to_none(
        self,
        store: DatasetPayloadStore,
    ) -> None:
        """Legacy manifests without ``schema_version`` deserialize with ``None``."""
        # Simulate an old manifest JSON (no schema_version key).
        import json

        old_manifest_json = json.dumps(
            {
                "dataset_id": "ds-legacy",
                "storage_mode": "file_shard_sparse",
                "shard_count": 1,
                "total_rows": 5,
                "schema_columns": [],
                "shards": [],
                "sample_index": {},
                "created_at": "2025-01-01T00:00:00Z",
            }
        ).encode("utf-8")

        key = store.get_manifest_key("ds-legacy", "org-42")
        await store._storage.put_bytes(
            object_name=key,
            data=old_manifest_json,
            content_type="application/json",
        )

        retrieved = await store.get_manifest("ds-legacy", "org-42")
        assert retrieved.schema_version is None

    async def test_get_nonexistent_manifest_raises(
        self,
        store: DatasetPayloadStore,
    ) -> None:
        with pytest.raises(FileNotFoundError):
            await store.get_manifest("does-not-exist", "org-42")


# ---------------------------------------------------------------------------
# Shard upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestShardUpload:
    """Upload a shard and verify the returned ShardEntry metadata."""

    async def test_put_shard_returns_correct_metadata(
        self,
        store: DatasetPayloadStore,
    ) -> None:
        data = b"fake-parquet-bytes-for-shard-0"
        entry = await store.put_shard(
            dataset_id="ds-test-001",
            org_id="org-42",
            shard_index=0,
            data=data,
            row_count=50,
        )

        assert entry.shard_index == 0
        assert entry.row_count == 50
        assert entry.format == "parquet"
        assert entry.byte_size == len(data)
        assert entry.checksum_sha256 == hashlib.sha256(data).hexdigest()
        assert isinstance(entry.uri, str)
        assert "shards/000000.parquet" in entry.uri

    async def test_put_shard_multiple_indices(
        self,
        store: DatasetPayloadStore,
    ) -> None:
        """Upload two shards and verify different URIs and checksums."""
        data0 = b"shard-zero-data"
        data1 = b"shard-one-data-here"

        entry0 = await store.put_shard(
            dataset_id="ds-multi",
            org_id="org-1",
            shard_index=0,
            data=data0,
            row_count=25,
        )
        entry1 = await store.put_shard(
            dataset_id="ds-multi",
            org_id="org-1",
            shard_index=1,
            data=data1,
            row_count=30,
        )

        assert entry0.shard_index == 0
        assert entry1.shard_index == 1
        assert entry0.uri != entry1.uri
        assert entry0.checksum_sha256 != entry1.checksum_sha256
        assert entry0.byte_size == len(data0)
        assert entry1.byte_size == len(data1)

    async def test_put_shard_custom_format(
        self,
        store: DatasetPayloadStore,
    ) -> None:
        data = b"some-arrow-data"
        entry = await store.put_shard(
            dataset_id="ds-fmt",
            org_id="org-1",
            shard_index=7,
            data=data,
            row_count=10,
            format="arrow",
        )
        assert entry.format == "arrow"
        assert "shards/000007.arrow" in entry.uri


# ---------------------------------------------------------------------------
# Deterministic delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDeterministicDelete:
    """Delete shards + manifest by reading the manifest then removing all."""

    async def test_delete_removes_shards_and_manifest(
        self,
        store: DatasetPayloadStore,
        storage: ArtifactStorage,
    ) -> None:
        manifest = DatasetManifest(
            dataset_id="ds-del-test",
            storage_mode="file_shard_sparse",
            shard_count=1,
            total_rows=10,
            shards=[],
        )
        await store.put_manifest(manifest, org_id="org-42")

        shard_entry = await store.put_shard(
            dataset_id="ds-del-test",
            org_id="org-42",
            shard_index=0,
            data=b"shard-data-to-delete",
            row_count=10,
        )
        manifest.shards = [shard_entry]
        await store.put_manifest(manifest, org_id="org-42")

        retrieved = await store.get_manifest("ds-del-test", "org-42")
        assert len(retrieved.shards) == 1

        # Act
        await store.delete_dataset_payload("ds-del-test", "org-42")

        with pytest.raises(FileNotFoundError):
            await store.get_manifest("ds-del-test", "org-42")

        with pytest.raises(FileNotFoundError):
            await storage.get_bytes(shard_entry.uri)

    async def test_delete_no_manifest_is_noop(
        self,
        store: DatasetPayloadStore,
    ) -> None:
        """Deleting a dataset that never had a manifest should not raise."""
        await store.delete_dataset_payload("never-created", "org-42")

    async def test_delete_already_deleted_is_noop(
        self,
        store: DatasetPayloadStore,
        storage: ArtifactStorage,
    ) -> None:
        """Deleting twice should be safe."""
        manifest = DatasetManifest(
            dataset_id="ds-del-twice",
            storage_mode="file_shard_sparse",
            shard_count=0,
            total_rows=0,
        )
        await store.put_manifest(manifest, org_id="org-42")
        await store.delete_dataset_payload("ds-del-twice", "org-42")
        await store.delete_dataset_payload("ds-del-twice", "org-42")


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestErrorHandling:
    """Store-level error conditions."""

    async def test_put_manifest_to_wrong_org_fails_to_get(
        self,
        store: DatasetPayloadStore,
        sample_manifest: DatasetManifest,
    ) -> None:
        await store.put_manifest(sample_manifest, org_id="org-42")
        with pytest.raises(FileNotFoundError):
            await store.get_manifest("ds-test-001", "org-99")
