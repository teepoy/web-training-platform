from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

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
    )

    assert report.ready
    dataset_reader.get_dataset.assert_awaited_once_with(
        "dataset-1",
        org_id="org-1",
    )
    readiness.assess_classes.assert_awaited_once_with(
        dataset=dataset,
        sample_ids=None,
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
