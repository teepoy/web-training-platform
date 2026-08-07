from __future__ import annotations

from typing import Any

from injector import inject

from app.modules.dataset_collections.domain.models import DatasetCollectionRevision
from app.modules.dataset_collections.port.local import (
    DatasetCollectionRevisionReaderPort,
)
from app.modules.datasets.port.dataset_reader import DatasetReader
from app.modules.training.app.services.readiness import TrainingReadinessService
from app.modules.training.domain.readiness import TrainingReadinessReport
from app.modules.training.domain.submission import (
    TrainingDatasetNotFoundError,
    TrainingReadinessError,
)
from app.shared.domain.data_source import RuntimeDataSourceRef


class TrainingPreflightService:
    """Run data-dependent readiness checks inside the durable workflow."""

    @inject
    def __init__(
        self,
        *,
        dataset_reader: DatasetReader,
        readiness: TrainingReadinessService,
        collection_revisions: DatasetCollectionRevisionReaderPort,
    ) -> None:
        self._dataset_reader = dataset_reader
        self._readiness = readiness
        self._collection_revisions = collection_revisions

    async def ensure_ready(
        self,
        *,
        dataset_id: str | None,
        collection_id: str | None,
        collection_revision_id: str | None,
        org_id: str,
        sample_ids: list[str] | None = None,
        sample_filter: dict[str, Any] | None = None,
    ) -> TrainingReadinessReport:
        source = RuntimeDataSourceRef.from_fields(
            dataset_id=dataset_id,
            collection_id=collection_id,
            collection_revision_id=collection_revision_id,
        )
        if source.kind == "dataset":
            assert source.dataset_id is not None
            dataset = await self._dataset_reader.get_dataset(
                source.dataset_id,
                org_id=org_id,
            )
            if dataset is None:
                raise TrainingDatasetNotFoundError(source.dataset_id)
            report = await self._readiness.assess_classes(
                dataset=dataset,
                sample_ids=sample_ids,
                sample_filter=sample_filter,
            )
        else:
            assert source.collection_id is not None
            assert source.collection_revision_id is not None
            revision = await self._collection_revisions.get_revision(
                source.collection_id,
                source.collection_revision_id,
                org_id,
            )
            report = self._revision_readiness(source.identity, revision)
        if not report.ready:
            raise TrainingReadinessError(report)
        return report

    @staticmethod
    def _revision_readiness(
        source_identity: str,
        revision: DatasetCollectionRevision,
    ) -> TrainingReadinessReport:
        active_labels = sorted(
            label for label, count in revision.label_counts.items() if count > 0
        )
        reasons = (
            ()
            if len(active_labels) >= 2
            else (f"training requires at least 2 active labels; got {active_labels}",)
        )
        annotated = sum(revision.label_counts.values())
        return TrainingReadinessReport(
            dataset_id=source_identity,
            annotated_samples=annotated,
            readable_samples=annotated,
            runtime_resolvable_samples=0,
            unusable_samples=0,
            skipped_samples=0,
            label_counts=dict(revision.label_counts),
            failure_reasons=reasons,
        )
