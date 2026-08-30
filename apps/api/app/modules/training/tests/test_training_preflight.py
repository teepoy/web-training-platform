from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.modules.dataset_collections.domain.models import DatasetCollectionRevision
from app.modules.training.app.services.preflight import TrainingPreflightService
from app.modules.training.domain.readiness import TrainingReadinessReport
from app.modules.training.domain.submission import TrainingReadinessError


def _report(*, ready: bool) -> TrainingReadinessReport:
    return TrainingReadinessReport(
        dataset_id="dataset-1",
        annotated_samples=2 if ready else 0,
        readable_samples=2 if ready else 0,
        runtime_resolvable_samples=0,
        unusable_samples=0,
        skipped_samples=0,
        label_counts={"a": 1, "b": 1} if ready else {},
        failure_reasons=() if ready else ("not ready",),
    )


@pytest.mark.asyncio
async def test_dataset_preflight_reuses_authorized_dataset_metadata() -> None:
    dataset = SimpleNamespace(id="dataset-1")
    dataset_reader = Mock()
    dataset_reader.get_dataset = AsyncMock(return_value=dataset)
    readiness = Mock()
    readiness.assess_classes = AsyncMock(return_value=_report(ready=True))
    service = TrainingPreflightService(
        dataset_reader=dataset_reader,
        readiness=readiness,
        collection_revisions=Mock(),
    )

    report = await service.ensure_ready(
        dataset_id="dataset-1",
        collection_id=None,
        collection_revision_id=None,
        org_id="org-1",
        sample_ids=["sample-1"],
    )

    assert report.ready
    dataset_reader.get_dataset.assert_awaited_once_with(
        "dataset-1",
        org_id="org-1",
    )
    readiness.assess_classes.assert_awaited_once_with(
        dataset=dataset,
        sample_ids=["sample-1"],
        sample_filter=None,
    )


@pytest.mark.asyncio
async def test_preflight_failure_is_a_workflow_failure() -> None:
    dataset_reader = Mock()
    dataset_reader.get_dataset = AsyncMock(return_value=SimpleNamespace(id="dataset-1"))
    readiness = Mock()
    readiness.assess_classes = AsyncMock(return_value=_report(ready=False))
    service = TrainingPreflightService(
        dataset_reader=dataset_reader,
        readiness=readiness,
        collection_revisions=Mock(),
    )

    with pytest.raises(TrainingReadinessError):
        await service.ensure_ready(
            dataset_id="dataset-1",
            collection_id=None,
            collection_revision_id=None,
            org_id="org-1",
        )


@pytest.mark.asyncio
async def test_collection_preflight_aggregates_current_selected_member_annotations() -> (
    None
):
    revision = DatasetCollectionRevision(
        id="revision-1",
        collection_id="collection-1",
        revision_number=1,
        definition_version=1,
        definition_hash="hash",
        target_view_id="patch_image_v1",
        target_view_contract="sc.patch-image",
        target_schema_version="1",
        status="ready",
        members=(
            {"member_id": "member-a", "source_dataset_id": "dataset-a"},
            {"member_id": "member-b", "source_dataset_id": "dataset-b"},
        ),
        manifest_uri="memory://revision.json",
        trigger_kind="manual",
        trigger_ref=None,
        created_by="user-1",
        created_at=datetime.now(UTC),
        error_code=None,
        error_detail=None,
    )
    collection_revisions = Mock()
    collection_revisions.get_revision = AsyncMock(return_value=revision)
    dataset_a = SimpleNamespace(id="dataset-a")
    dataset_b = SimpleNamespace(id="dataset-b")
    dataset_reader = Mock()
    dataset_reader.get_dataset = AsyncMock(
        side_effect=lambda dataset_id, **_: {
            "dataset-a": dataset_a,
            "dataset-b": dataset_b,
        }[dataset_id]
    )
    readiness = Mock()
    readiness.assess_classes = AsyncMock(
        side_effect=[
            TrainingReadinessReport(
                dataset_id="dataset-b",
                annotated_samples=5,
                readable_samples=5,
                runtime_resolvable_samples=0,
                unusable_samples=0,
                skipped_samples=0,
                label_counts={"scratch": 2, "particle": 3},
                failure_reasons=(),
            )
        ]
    )
    service = TrainingPreflightService(
        dataset_reader=dataset_reader,
        readiness=readiness,
        collection_revisions=collection_revisions,
    )

    report = await service.ensure_ready(
        dataset_id=None,
        collection_id="collection-1",
        collection_revision_id="revision-1",
        collection_member_ids=["member-b"],
        org_id="org-1",
    )

    assert report.label_counts == {"scratch": 2, "particle": 3}
    dataset_reader.get_dataset.assert_awaited_once_with("dataset-b", org_id="org-1")
    readiness.assess_classes.assert_awaited_once_with(
        dataset=dataset_b,
        sample_ids=None,
        sample_filter=None,
    )


@pytest.mark.asyncio
async def test_collection_preflight_normalizes_namespaced_selection_per_member() -> None:
    revision = DatasetCollectionRevision(
        id="revision-1",
        collection_id="collection-1",
        revision_number=1,
        definition_version=1,
        definition_hash="hash",
        target_view_id="patch_image_v1",
        target_view_contract="sc.patch-image",
        target_schema_version="1",
        status="ready",
        members=(
            {"member_id": "member-a", "source_dataset_id": "dataset-a"},
            {"member_id": "member-b", "source_dataset_id": "dataset-b"},
        ),
        manifest_uri="memory://revision.json",
        trigger_kind="manual",
        trigger_ref=None,
        created_by="user-1",
        created_at=datetime.now(UTC),
        error_code=None,
        error_detail=None,
    )
    collection_revisions = Mock()
    collection_revisions.get_revision = AsyncMock(return_value=revision)
    datasets = {
        "dataset-a": SimpleNamespace(id="dataset-a"),
        "dataset-b": SimpleNamespace(id="dataset-b"),
    }
    dataset_reader = Mock()
    dataset_reader.get_dataset = AsyncMock(
        side_effect=lambda dataset_id, **_: datasets[dataset_id]
    )
    readiness = Mock()
    readiness.assess_classes = AsyncMock(return_value=_report(ready=True))
    service = TrainingPreflightService(
        dataset_reader=dataset_reader,
        readiness=readiness,
        collection_revisions=collection_revisions,
    )
    collection_filter = {
        "combinator": "and",
        "items": [
            {
                "kind": "condition",
                "field": "row_key",
                "condition": {
                    "filterType": "set",
                    "values": ["dataset-a::sample-a", "dataset-b::sample-b"],
                    "exclude": False,
                },
            },
            {
                "kind": "group",
                "combinator": "or",
                "items": [
                    {
                        "kind": "condition",
                        "field": "final_class",
                        "condition": {
                            "filterType": "set",
                            "values": ["Scratch"],
                            "exclude": True,
                        },
                    }
                ],
            },
        ],
    }

    await service.ensure_ready(
        dataset_id=None,
        collection_id="collection-1",
        collection_revision_id="revision-1",
        collection_member_ids=["member-a", "member-b"],
        org_id="org-1",
        sample_ids=["dataset-a::sample-a", "dataset-b::sample-b"],
        sample_filter=collection_filter,
    )

    calls_by_dataset = {
        call.kwargs["dataset"].id: call.kwargs
        for call in readiness.assess_classes.await_args_list
    }
    assert calls_by_dataset["dataset-a"]["sample_ids"] == ["sample-a"]
    assert calls_by_dataset["dataset-b"]["sample_ids"] == ["sample-b"]
    assert calls_by_dataset["dataset-a"]["sample_filter"] == {
        **collection_filter,
        "items": [
            {
                **collection_filter["items"][0],
                "condition": {
                    **collection_filter["items"][0]["condition"],
                    "values": ["sample-a"],
                },
            },
            collection_filter["items"][1],
        ],
    }
    assert calls_by_dataset["dataset-b"]["sample_filter"] == {
        **collection_filter,
        "items": [
            {
                **collection_filter["items"][0],
                "condition": {
                    **collection_filter["items"][0]["condition"],
                    "values": ["sample-b"],
                },
            },
            collection_filter["items"][1],
        ],
    }
    assert collection_filter["items"][0]["condition"]["values"] == [
        "dataset-a::sample-a",
        "dataset-b::sample-b",
    ]
