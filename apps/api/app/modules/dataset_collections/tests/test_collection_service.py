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
    DatasetCollectionRevision,
    NewCollectionMember,
)
from app.modules.dataset_collections.domain.errors import DatasetCollectionNotFoundError
from app.modules.datasets.domain.entities import (
    DatasetRevision,
    DatasetRevisionOperation,
)
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
        dataset_revision_reader=AsyncMock(),
        artifact_storage=artifact_storage,
    )

    await service.delete_collection("collection-1", "org-1", actor_id="user-1")

    repository.delete_collection.assert_awaited_once_with("collection-1", "org-1")
    assert {awaited.args[0] for awaited in artifact_storage.delete.await_args_list} == {
        "memory://data.parquet",
        "memory://provenance.parquet",
    }


@pytest.mark.asyncio
async def test_snapshot_update_status_detects_changed_revisions_in_one_batch() -> None:
    repository = AsyncMock()
    repository.get_collection.return_value = _collection()
    repository.get_current_revision.return_value = DatasetCollectionRevision(
        id="snapshot-1",
        collection_id="collection-1",
        revision_number=1,
        definition_version=1,
        definition_hash="hash-1",
        target_view_id="patch_image_v1",
        target_view_contract="sc.patch-image",
        target_schema_version="1",
        status="ready",
        source_snapshot=(
            {
                "member_id": "member-1",
                "source_dataset_id": "dataset-1",
                "dataset_revision_id": "dataset-revision-1",
                "dataset_revision_number": 1,
            },
            {
                "member_id": "member-2",
                "source_dataset_id": "dataset-2",
                "dataset_revision_id": "dataset-revision-2",
                "dataset_revision_number": 2,
            },
        ),
        row_count=None,
        label_counts={},
        manifest_uri="memory://snapshot-1.json",
        provenance_uri=None,
        trigger_kind="manual",
        trigger_ref=None,
        created_by="user-1",
        created_at=_now(),
        error_code=None,
        error_detail=None,
        manifest_format="collection-composite-observed.v1",
        source_resolution="observed",
        reproducibility_capability=False,
    )
    dataset_revision_reader = AsyncMock()
    dataset_revision_reader.list_current.return_value = {
        "dataset-1": DatasetRevision(
            id="dataset-revision-3",
            dataset_id="dataset-1",
            revision_number=3,
            manifest_uri="memory://dataset-revision-3.json",
            operation=DatasetRevisionOperation.BATCH_EDIT,
            created_by="user-1",
            created_at=_now(),
        ),
        "dataset-2": DatasetRevision(
            id="dataset-revision-2",
            dataset_id="dataset-2",
            revision_number=2,
            manifest_uri="memory://dataset-revision-2.json",
            operation=DatasetRevisionOperation.INITIAL_IMPORT,
            created_by="user-1",
            created_at=_now(),
        ),
    }
    service = DatasetCollectionService(
        repository=repository,
        dataset_reader=AsyncMock(),
        dataset_revision_reader=dataset_revision_reader,
        artifact_storage=AsyncMock(),
    )

    status = await service.get_snapshot_update_status("collection-1", "org-1")

    assert status.snapshot_id == "snapshot-1"
    assert status.update_available is True
    assert status.outdated_member_count == 1
    assert [item.dataset_id for item in status.members if item.update_available] == [
        "dataset-1"
    ]
    assert status.members[0].observed_dataset_revision_id == "dataset-revision-1"
    assert status.members[0].current_dataset_revision_id == "dataset-revision-3"
    dataset_revision_reader.list_current.assert_awaited_once_with(
        ("dataset-1", "dataset-2"), "org-1"
    )
    assert dataset_revision_reader.get_current.await_count == 0


@pytest.mark.asyncio
async def test_snapshot_update_status_does_not_backfill_legacy_dataset_revisions() -> None:
    repository = AsyncMock()
    repository.get_collection.return_value = _collection()
    repository.get_current_revision.return_value = DatasetCollectionRevision(
        id="legacy-snapshot",
        collection_id="collection-1",
        revision_number=1,
        definition_version=1,
        definition_hash="legacy-hash",
        target_view_id="patch_image_v1",
        target_view_contract="sc.patch-image",
        target_schema_version="1",
        status="ready",
        source_snapshot=(
            {"member_id": "member-1", "source_dataset_id": "dataset-1"},
        ),
        row_count=10,
        label_counts={},
        manifest_uri="memory://legacy.parquet",
        provenance_uri="memory://legacy-provenance.parquet",
        trigger_kind="manual",
        trigger_ref=None,
        created_by="user-1",
        created_at=_now(),
        error_code=None,
        error_detail=None,
    )
    dataset_revision_reader = AsyncMock()
    dataset_revision_reader.list_current.return_value = {}
    service = DatasetCollectionService(
        repository=repository,
        dataset_reader=AsyncMock(),
        dataset_revision_reader=dataset_revision_reader,
        artifact_storage=AsyncMock(),
    )

    status = await service.get_snapshot_update_status("collection-1", "org-1")

    assert status.update_available is False
    assert status.members[0].observed_dataset_revision_id is None
    assert status.members[0].current_dataset_revision_id is None
    assert dataset_revision_reader.resolve_or_create_baseline.await_count == 0


@pytest.mark.asyncio
async def test_revision_persistence_failure_cleans_composite_manifest() -> None:
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
    artifact_storage.get_bytes.return_value = json.dumps(
        {"artifact": {"row_count": 1}}
    ).encode("utf-8")
    dataset = Dataset(
        id="dataset-1",
        name="Dataset",
        dataset_type="image_sc",
        task_spec=TaskSpec(task_type="sc", label_space=["clean", "defect"]),
        view_types=["patch_image_v1"],
        org_id="org-1",
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
    )
    dataset_reader = AsyncMock()
    dataset_reader.get_dataset.return_value = dataset
    dataset_revision_reader = AsyncMock()
    dataset_revision_reader.list_current.return_value = {}
    dataset_revision_reader.resolve_or_create_baseline.return_value = DatasetRevision(
        id="dataset-revision-1",
        dataset_id=dataset.id,
        revision_number=3,
        manifest_uri="memory://dataset-revision-manifest.json",
        operation=DatasetRevisionOperation.LEGACY_BASELINE,
        created_by="user-1",
        created_at=_now(),
    )
    service = DatasetCollectionService(
        repository=repository,
        dataset_reader=dataset_reader,
        dataset_revision_reader=dataset_revision_reader,
        artifact_storage=artifact_storage,
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await service.publish_snapshot_for_automation(
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
    assert uploaded["manifest_format"] == "collection-composite-observed.v1"
    assert uploaded["source_resolution"] == "observed"
    assert uploaded["reproducibility"]["capability"] is False
    assert member["dataset_revision_id"] == "dataset-revision-1"
    assert member["dataset_revision_number"] == 3
    assert member["dataset_revision_manifest_uri"] == (
        "memory://dataset-revision-manifest.json"
    )
    assert member["dataset_revision_binding"] == "observed"
    assert member["dataset_revision_reproducible"] is False
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
    )
    service = DatasetCollectionService(
        repository=repository,
        dataset_reader=dataset_reader,
        dataset_revision_reader=AsyncMock(),
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
