from __future__ import annotations

import uuid

import pyarrow as pa
import pytest

from app.modules.storage.adapter.sparse.import_operator import (
    SparseImportOperator,
)
from app.shared.infrastructure.storage.memory import InMemoryArtifactStorage
from app.modules.storage.domain.sparse.models import SampleLocator
from app.modules.storage.domain.sparse.store import DatasetPayloadStore


# ── fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def storage() -> InMemoryArtifactStorage:
    return InMemoryArtifactStorage()


@pytest.fixture
def payload_store(storage: InMemoryArtifactStorage) -> DatasetPayloadStore:
    return DatasetPayloadStore(storage)


@pytest.fixture
def dataset_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def org_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def pyarrow_schema() -> pa.Schema:
    return pa.schema([
        ("defect_id", pa.string()),
        ("image_uris", pa.string()),
        ("label", pa.string()),
    ])


@pytest.fixture
def operator(
    dataset_id: str,
    org_id: str,
    payload_store: DatasetPayloadStore,
) -> SparseImportOperator:
    return SparseImportOperator(
        dataset_id=dataset_id,
        org_id=org_id,
        payload_store=payload_store,
    )


# ── tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_flush_shard(
    operator: SparseImportOperator,
    pyarrow_schema: pa.Schema,
    dataset_id: str,
) -> None:
    """Flush 5 rows → verify ShardEntry metadata and locators."""
    rows = [
        {"defect_id": f"d-{i:03d}", "image_uris": f"memory://img/{i}.png", "label": "cat"}
        for i in range(5)
    ]

    shard_entry, locators = await operator.flush_shard(
        shard_index=0,
        rows=rows,
        pyarrow_schema=pyarrow_schema,
        row_id_key="defect_id",
    )

    assert shard_entry.row_count == 5
    assert shard_entry.format == "parquet"
    assert shard_entry.shard_index == 0
    assert shard_entry.uri.startswith("memory://")

    # Verify locators
    assert len(locators) == 5
    for i, row in enumerate(rows):
        item_id = row["defect_id"]
        assert item_id in locators
        loc = locators[item_id]
        assert isinstance(loc, SampleLocator)
        assert loc.dataset_id == dataset_id
        assert loc.shard_index == 0
        assert loc.row_index == i
        assert loc.upstream_item_id == item_id


@pytest.mark.asyncio
async def test_flush_shard_custom_row_id_key(
    dataset_id: str,
    org_id: str,
    payload_store: DatasetPayloadStore,
) -> None:
    """Flush with row_id_key='sample_id' → locators keyed by sample_id."""
    operator = SparseImportOperator(
        dataset_id=dataset_id,
        org_id=org_id,
        payload_store=payload_store,
    )
    schema = pa.schema([
        ("sample_id", pa.string()),
        ("value", pa.int64()),
    ])
    rows = [
        {"sample_id": "abc-001", "value": 42},
        {"sample_id": "abc-002", "value": 99},
    ]

    _shard_entry, locators = await operator.flush_shard(
        shard_index=0,
        rows=rows,
        pyarrow_schema=schema,
        row_id_key="sample_id",
    )

    assert "abc-001" in locators
    assert "abc-002" in locators
    assert locators["abc-001"].upstream_item_id == "abc-001"
    assert locators["abc-001"].shard_index == 0
    assert locators["abc-001"].row_index == 0
    assert locators["abc-002"].row_index == 1


@pytest.mark.asyncio
async def test_finalize_manifest_empty_shards(
    dataset_id: str,
    org_id: str,
    payload_store: DatasetPayloadStore,
) -> None:
    """Finalize manifest with zero shards, zero rows."""
    operator = SparseImportOperator(
        dataset_id=dataset_id,
        org_id=org_id,
        payload_store=payload_store,
    )

    manifest = await operator.finalize_manifest(
        shard_entries=[],
        sample_index={},
        total_rows=0,
        shard_count=0,
        schema_columns=[],
        schema_version="v1",
    )

    assert manifest.total_rows == 0
    assert manifest.shard_count == 0
    assert manifest.shards == []
    assert manifest.sample_index == {}

    reloaded = await payload_store.get_manifest(dataset_id, org_id)
    assert reloaded.total_rows == 0
    assert reloaded.shard_count == 0
