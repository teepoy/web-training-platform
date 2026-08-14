from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import polars as pl
import pytest

from app.modules.dataset_collections.app.services.collection_service import (
    DatasetCollectionService,
)
from app.modules.dataset_collections.domain.models import (
    DatasetCollection,
    DatasetCollectionMember,
)
from app.shared.api.schemas import Dataset, TaskSpec


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _collection() -> DatasetCollection:
    return DatasetCollection(
        id="collection-1",
        org_id="org-1",
        name="Collection",
        description="",
        target_view_id="patch_image_v1",
        target_view_contract="sc.patch-image",
        target_schema_version="1",
        duplicate_policy="keep_all",
        missing_data_policy="fail",
        definition_version=1,
        created_by="user-1",
        created_at=_now(),
        updated_at=_now(),
    )


@pytest.mark.asyncio
async def test_delete_collection_cleans_revision_artifacts_after_database_delete() -> None:
    repository = AsyncMock()
    repository.get_collection.return_value = _collection()
    repository.delete_collection.return_value = (
        "memory://data.parquet",
        "memory://provenance.parquet",
    )
    artifact_storage = AsyncMock()
    service = DatasetCollectionService(
        repository=repository,
        dataset_reader=AsyncMock(),
        storage_factory=AsyncMock(),
        artifact_storage=artifact_storage,
    )

    await service.delete_collection("collection-1", "org-1", actor_id="user-1")

    repository.delete_collection.assert_awaited_once_with("collection-1", "org-1")
    assert {
        awaited.args[0] for awaited in artifact_storage.delete.await_args_list
    } == {"memory://data.parquet", "memory://provenance.parquet"}


@pytest.mark.asyncio
async def test_revision_upload_failure_cleans_already_uploaded_data_artifact() -> None:
    artifact_storage = AsyncMock()
    artifact_storage.put_file.side_effect = [
        "memory://data.parquet",
        RuntimeError("provenance upload failed"),
    ]
    storage = AsyncMock()
    storage.list_samples.return_value = pl.DataFrame(
        {"sample_id": ["sample-1"], "label": ["clean"]}
    ).lazy()
    storage_factory = AsyncMock()
    storage_factory.open.return_value = storage
    service = DatasetCollectionService(
        repository=AsyncMock(),
        dataset_reader=AsyncMock(),
        storage_factory=storage_factory,
        artifact_storage=artifact_storage,
    )
    member = DatasetCollectionMember(
        id="member-1",
        collection_id="collection-1",
        source_dataset_id="dataset-1",
        position=0,
        linked_definition_version=1,
        unlinked_definition_version=None,
        filter_spec={},
        label_mapping={},
        sampling_spec={},
        linked_by="user-1",
        linked_at=_now(),
        unlinked_by=None,
        unlinked_at=None,
    )
    dataset = Dataset(
        id="dataset-1",
        name="Dataset",
        dataset_type="image_sc",
        task_spec=TaskSpec(task_type="sc", label_space=["clean", "defect"]),
        view_types=["patch_image_v1"],
        org_id="org-1",
    )

    with pytest.raises(RuntimeError, match="provenance upload failed"):
        await service._materialize_revision(
            collection=_collection(),
            revision_id="revision-1",
            members=[member],
            datasets={dataset.id: dataset},
        )

    artifact_storage.delete.assert_awaited_once_with("memory://data.parquet")
