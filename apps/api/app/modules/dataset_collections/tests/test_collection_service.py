from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from unittest.mock import AsyncMock

import pytest

from app.modules.dataset_collections.app.services.collection_service import (
    DatasetCollectionService,
)
from app.modules.dataset_collections.domain.models import (
    DatasetCollection,
    DatasetCollectionMember,
    NewCollectionMember,
)
from app.modules.dataset_collections.domain.errors import DatasetCollectionNotFoundError
from app.modules.dataset_collections.domain.errors import DatasetCollectionValidationError
from app.shared.api.schemas import Dataset, DatasetStorageMode, TaskSpec


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
async def test_delete_collection_cleans_revision_artifacts_after_database_delete() -> (
    None
):
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
        artifact_storage=artifact_storage,
    )

    await service.delete_collection("collection-1", "org-1", actor_id="user-1")

    repository.delete_collection.assert_awaited_once_with("collection-1", "org-1")
    assert {awaited.args[0] for awaited in artifact_storage.delete.await_args_list} == {
        "memory://data.parquet",
        "memory://provenance.parquet",
    }


@pytest.mark.asyncio
async def test_revision_persistence_failure_cleans_membership_manifest() -> None:
    repository = AsyncMock()
    repository.get_collection.return_value = _collection()
    repository.list_active_members.return_value = [
        DatasetCollectionMember(
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
    ]
    repository.get_current_revision.return_value = None
    repository.next_revision_number.return_value = 1
    repository.create_revision.side_effect = RuntimeError("database unavailable")
    artifact_storage = AsyncMock()
    artifact_storage.put_bytes.return_value = "memory://collection-manifest.json"
    dataset = Dataset(
        id="dataset-1",
        name="Dataset",
        dataset_type="image_sc",
        task_spec=TaskSpec(task_type="sc", label_space=["clean", "defect"]),
        view_types=["patch_image_v1"],
        org_id="org-1",
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
        dataset_meta={
            "source_inspection_time": "2026-08-01T04:00:00+08:00",
            "source_wafer_key": 1,
        },
    )
    dataset_reader = AsyncMock()
    dataset_reader.get_dataset.return_value = dataset
    service = DatasetCollectionService(
        repository=repository,
        dataset_reader=dataset_reader,
        artifact_storage=artifact_storage,
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await service.publish_revision_for_automation(
            "collection-1",
            "org-1",
            actor_id="user-2",
            expected_definition_version=1,
            trigger_kind="manual",
            trigger_ref=None,
        )

    artifact_storage.delete.assert_awaited_once_with(
        "memory://collection-manifest.json"
    )
    uploaded = json.loads(artifact_storage.put_bytes.await_args.args[1])
    member = uploaded["members"][0]
    assert uploaded["manifest_format"] == "collection-revision-membership.v1"
    assert member == {
        "member_id": "member-1",
        "source_dataset_id": "dataset-1",
        "position": 0,
        "filter_spec": {},
        "label_mapping": {},
        "sampling_spec": {},
    }
    assert "summary" not in uploaded
    artifact_storage.get_bytes.assert_not_awaited()
    assert artifact_storage.put_file.await_count == 0


@pytest.mark.asyncio
async def test_automation_admission_allows_org_non_creator_but_rejects_cross_org() -> (
    None
):
    collection = _collection()
    repository = AsyncMock()
    repository.get_collection.side_effect = lambda collection_id, org_id: (
        collection
        if collection_id == collection.id and org_id == collection.org_id
        else None
    )
    repository.list_active_members.return_value = []
    linked_member = DatasetCollectionMember(
        id="member-1",
        collection_id=collection.id,
        source_dataset_id="dataset-1",
        position=0,
        linked_definition_version=2,
        unlinked_definition_version=None,
        filter_spec={},
        label_mapping={},
        sampling_spec={},
        linked_by="user-2",
        linked_at=_now(),
        unlinked_by=None,
        unlinked_at=None,
    )
    repository.link_members.return_value = (
        replace(collection, definition_version=2),
        [linked_member],
    )
    dataset_reader = AsyncMock()
    dataset_reader.get_dataset.return_value = Dataset(
        id="dataset-1",
        name="Dataset",
        dataset_type="image_sc",
        task_spec=TaskSpec(task_type="sc", label_space=["clean", "defect"]),
        view_types=["patch_image_v1"],
        org_id="org-1",
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
        dataset_meta={
            "source_inspection_time": "2026-08-01T04:00:00+08:00",
            "source_wafer_key": 1,
        },
    )
    service = DatasetCollectionService(
        repository=repository,
        dataset_reader=dataset_reader,
        artifact_storage=AsyncMock(),
    )
    request = (NewCollectionMember(source_dataset_id="dataset-1", position=0),)

    _, members = await service.admit_members_for_automation(
        collection.id,
        collection.org_id,
        actor_id="user-2",
        expected_definition_version=1,
        members=request,
    )

    assert members == [linked_member]
    repository.link_members.assert_awaited_once_with(
        collection.id,
        collection.org_id,
        expected_definition_version=1,
        members=request,
        actor_id="user-2",
    )
    with pytest.raises(DatasetCollectionNotFoundError):
        await service.admit_members_for_automation(
            collection.id,
            "org-2",
            actor_id="user-2",
            expected_definition_version=1,
            members=request,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("storage_mode", "dataset_meta", "expected_code"),
    [
        (DatasetStorageMode.DB_FULL, {}, "collection_member_storage_unsupported"),
        (
            DatasetStorageMode.FILE_SHARD_SPARSE,
            {},
            "collection_member_inspection_identity_required",
        ),
    ],
)
async def test_collection_rejects_members_without_sparse_sc_inspection_identity(
    storage_mode: DatasetStorageMode,
    dataset_meta: dict[str, object],
    expected_code: str,
) -> None:
    collection = _collection()
    repository = AsyncMock()
    repository.get_collection.return_value = collection
    repository.list_active_members.return_value = []
    dataset_reader = AsyncMock()
    dataset_reader.get_dataset.return_value = Dataset(
        id="dataset-1",
        name="Dataset",
        dataset_type="image_sc",
        task_spec=TaskSpec(task_type="sc", label_space=["clean", "defect"]),
        view_types=["patch_image_v1"],
        org_id="org-1",
        storage_mode=storage_mode,
        dataset_meta=dataset_meta,
    )
    service = DatasetCollectionService(
        repository=repository,
        dataset_reader=dataset_reader,
        artifact_storage=AsyncMock(),
    )

    with pytest.raises(DatasetCollectionValidationError) as error:
        await service.link_members(
            collection.id,
            collection.org_id,
            actor_id=collection.created_by,
            expected_definition_version=collection.definition_version,
            members=(NewCollectionMember(source_dataset_id="dataset-1", position=0),),
        )

    assert error.value.code == expected_code
    repository.link_members.assert_not_awaited()
