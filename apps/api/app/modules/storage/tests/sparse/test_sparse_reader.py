"""Baseline tests for SparseManifestReader (parquet shard reader).

Tests cover schema reading, row batch retrieval with column projection,
single-row access, and error handling for out-of-range indices and
missing shards.

Uses in-memory parquet bytes — no disk I/O or compose services needed.
"""

from __future__ import annotations

import io
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.modules.storage.domain.sparse.models import ColumnSchema
from app.modules.storage.domain.sparse.reader import SparseManifestReader

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helper: build a small in-memory parquet file as bytes
# ---------------------------------------------------------------------------


def _make_parquet_bytes(
    num_rows: int = 5,
    extra_columns: list[tuple[str, list[object]]] | None = None,
) -> bytes:
    """Create a tiny parquet file in memory and return its raw bytes."""
    columns: list[tuple[str, list[object]]] = [
        ("sample_id", [f"s{i}" for i in range(num_rows)]),
        ("label", [f"class-{i % 3}" for i in range(num_rows)]),
        ("confidence", [round(i / num_rows, 2) for i in range(num_rows)]),
    ]
    if extra_columns:
        columns.extend(extra_columns)

    arrays = [pa.array(vals) for _, vals in columns]
    names = [name for name, _ in columns]
    table = pa.table(dict(zip(names, arrays)))

    buf = io.BytesIO()
    pq.write_table(table, buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# In-memory ArtifactStorage mock
# ---------------------------------------------------------------------------


class _InMemoryShardStore:
    """Stores parquet bytes keyed by shard URI for testing."""

    def __init__(self) -> None:
        self._shards: dict[str, bytes] = {}

    def add_shard(self, uri: str, data: bytes) -> None:
        self._shards[uri] = data

    async def get_bytes(self, uri: str) -> bytes:
        if uri not in self._shards:
            raise FileNotFoundError(f"Shard not found: {uri}")
        return self._shards[uri]

    async def put_bytes(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        self._shards[object_name] = data
        return f"memory://{object_name}"

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
        self._shards.pop(uri, None)

    async def list_prefix(self, prefix: str) -> list[str]:
        return [f"memory://{k}" for k in self._shards if k.startswith(prefix)]


@pytest.fixture
def reader() -> SparseManifestReader:
    return SparseManifestReader()


@pytest.fixture
def shard_store() -> _InMemoryShardStore:
    return _InMemoryShardStore()


@pytest.fixture
def parquet_bytes() -> bytes:
    """Standard 5-row test parquet with sample_id, label, confidence."""
    return _make_parquet_bytes(num_rows=5)


@pytest.fixture
def shard_uri(parquet_bytes: bytes, shard_store: _InMemoryShardStore) -> str:
    uri = "memory://test-shard-000000.parquet"
    shard_store.add_shard(uri, parquet_bytes)
    return uri


# ---------------------------------------------------------------------------
# Schema reading
# ---------------------------------------------------------------------------


class TestReadShardSchema:
    """read_shard_schema returns column name/type pairs."""

    async def test_returns_column_schemas(
        self,
        reader: SparseManifestReader,
        shard_uri: str,
        shard_store: _InMemoryShardStore,
    ) -> None:
        schemas = await reader.read_shard_schema(
            shard_uri,
            shard_store,
        )
        assert isinstance(schemas, list)
        assert all(isinstance(s, ColumnSchema) for s in schemas)
        names = [s.name for s in schemas]
        assert "sample_id" in names
        assert "label" in names
        assert "confidence" in names

    async def test_type_strings_are_nonempty(
        self,
        reader: SparseManifestReader,
        shard_uri: str,
        shard_store: _InMemoryShardStore,
    ) -> None:
        schemas = await reader.read_shard_schema(
            shard_uri,
            shard_store,
        )
        for s in schemas:
            assert isinstance(s.type, str)
            assert len(s.type) > 0

    async def test_missing_shard_raises(
        self,
        reader: SparseManifestReader,
        shard_store: _InMemoryShardStore,
    ) -> None:
        with pytest.raises(FileNotFoundError):
            await reader.read_shard_schema(
                "memory://nonexistent.parquet",
                shard_store,
            )


# ---------------------------------------------------------------------------
# Shard summary
# ---------------------------------------------------------------------------


class TestReadShardSummary:
    """read_shard_summary returns row count, row groups, column names."""

    async def test_summary_has_expected_keys(
        self,
        reader: SparseManifestReader,
        shard_uri: str,
        shard_store: _InMemoryShardStore,
    ) -> None:
        summary: dict[str, object] = await reader.read_shard_summary(
            shard_uri,
            shard_store,
        )
        assert isinstance(summary["row_count"], int)
        assert summary["row_count"] == 5
        assert isinstance(summary["row_groups"], int)
        assert summary["row_groups"] >= 1
        assert isinstance(summary["column_names"], list)
        assert "sample_id" in summary["column_names"]
        assert "label" in summary["column_names"]
        assert "confidence" in summary["column_names"]
        assert isinstance(summary["approx_byte_size"], int)
        assert summary["approx_byte_size"] > 0


# ---------------------------------------------------------------------------
# Row batch reading
# ---------------------------------------------------------------------------


class TestReadRowBatch:
    """read_row_batch returns correct rows with optional column projection."""

    async def test_read_all_rows(
        self,
        reader: SparseManifestReader,
        shard_uri: str,
        shard_store: _InMemoryShardStore,
    ) -> None:
        rows = await reader.read_row_batch(
            shard_uri,
            start=0,
            count=5,
            storage=shard_store,
        )
        assert len(rows) == 5

    async def test_column_projection(
        self,
        reader: SparseManifestReader,
        shard_uri: str,
        shard_store: _InMemoryShardStore,
    ) -> None:
        rows = await reader.read_row_batch(
            shard_uri,
            start=0,
            count=3,
            storage=shard_store,
            columns=["sample_id", "confidence"],
        )
        assert len(rows) == 3
        for row in rows:
            assert set(row.keys()) == {"sample_id", "confidence"}
            assert "label" not in row

    async def test_read_arbitrary_rows_once(
        self,
        reader: SparseManifestReader,
        shard_uri: str,
        shard_store: _InMemoryShardStore,
    ) -> None:
        rows = await reader.read_rows(
            shard_uri,
            row_indices=[4, 1],
            storage=shard_store,
            columns=["sample_id"],
        )

        assert rows == {
            4: {"sample_id": "s4"},
            1: {"sample_id": "s1"},
        }

    async def test_partial_row_batch(
        self,
        reader: SparseManifestReader,
        shard_uri: str,
        shard_store: _InMemoryShardStore,
    ) -> None:
        rows = await reader.read_row_batch(
            shard_uri,
            start=2,
            count=2,
            storage=shard_store,
        )
        assert len(rows) == 2
        assert rows[0]["sample_id"] == "s2"
        assert rows[1]["sample_id"] == "s3"

    async def test_batch_beyond_end_returns_fewer(
        self,
        reader: SparseManifestReader,
        shard_uri: str,
        shard_store: _InMemoryShardStore,
    ) -> None:
        rows = await reader.read_row_batch(
            shard_uri,
            start=3,
            count=10,
            storage=shard_store,
        )
        assert len(rows) == 2

    async def test_start_past_end_returns_empty(
        self,
        reader: SparseManifestReader,
        shard_uri: str,
        shard_store: _InMemoryShardStore,
    ) -> None:
        rows = await reader.read_row_batch(
            shard_uri,
            start=100,
            count=5,
            storage=shard_store,
        )
        assert rows == []

    async def test_column_projection_none_returns_all(
        self,
        reader: SparseManifestReader,
        shard_uri: str,
        shard_store: _InMemoryShardStore,
    ) -> None:
        """columns=None should return all columns."""
        rows = await reader.read_row_batch(
            shard_uri,
            start=0,
            count=1,
            storage=shard_store,
            columns=None,
        )
        assert len(rows) == 1
        assert "sample_id" in rows[0]
        assert "label" in rows[0]
        assert "confidence" in rows[0]

    async def test_missing_shard_raises(
        self,
        reader: SparseManifestReader,
        shard_store: _InMemoryShardStore,
    ) -> None:
        with pytest.raises(FileNotFoundError):
            await reader.read_row_batch(
                "memory://ghost.parquet",
                start=0,
                count=1,
                storage=shard_store,
            )


# ---------------------------------------------------------------------------
# Single row access
# ---------------------------------------------------------------------------


class TestReadRow:
    """read_row returns a single row as dict."""

    async def test_read_row_returns_correct_values(
        self,
        reader: SparseManifestReader,
        shard_uri: str,
        shard_store: _InMemoryShardStore,
    ) -> None:
        row = await reader.read_row(
            shard_uri,
            row_index=0,
            storage=shard_store,
        )
        assert row["sample_id"] == "s0"
        assert row["label"] == "class-0"

        row2 = await reader.read_row(
            shard_uri,
            row_index=4,
            storage=shard_store,
        )
        assert row2["sample_id"] == "s4"

    async def test_read_row_out_of_range_negative(
        self,
        reader: SparseManifestReader,
        shard_uri: str,
        shard_store: _InMemoryShardStore,
    ) -> None:
        with pytest.raises(IndexError, match="out of range"):
            await reader.read_row(
                shard_uri,
                row_index=-1,
                storage=shard_store,
            )

    async def test_read_row_out_of_range_positive(
        self,
        reader: SparseManifestReader,
        shard_uri: str,
        shard_store: _InMemoryShardStore,
    ) -> None:
        with pytest.raises(IndexError, match="out of range"):
            await reader.read_row(
                shard_uri,
                row_index=99,
                storage=shard_store,
            )


# ---------------------------------------------------------------------------
# Multiple shards / real-world scenarios
# ---------------------------------------------------------------------------


class TestMultiShardScenarios:
    """Read from different shard files with varying schemas."""

    async def test_two_shards_same_schema(
        self,
        reader: SparseManifestReader,
        shard_store: _InMemoryShardStore,
    ) -> None:
        data1 = _make_parquet_bytes(num_rows=3)
        data2 = _make_parquet_bytes(num_rows=7)
        shard_store.add_shard("memory://shard0.parquet", data1)
        shard_store.add_shard("memory://shard1.parquet", data2)

        rows0 = await reader.read_row_batch(
            "memory://shard0.parquet",
            start=0,
            count=10,
            storage=shard_store,
        )
        rows1 = await reader.read_row_batch(
            "memory://shard1.parquet",
            start=0,
            count=10,
            storage=shard_store,
        )
        assert len(rows0) == 3
        assert len(rows1) == 7
