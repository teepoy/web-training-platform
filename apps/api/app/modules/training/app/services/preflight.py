from __future__ import annotations

import asyncio
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


def _normalize_collection_row_keys(
    value: Any,
    *,
    source_dataset_id: str,
) -> Any:
    if isinstance(value, list):
        return [
            _normalize_collection_row_keys(item, source_dataset_id=source_dataset_id)
            for item in value
        ]
    if not isinstance(value, dict):
        return value

    normalized = {
        key: _normalize_collection_row_keys(item, source_dataset_id=source_dataset_id)
        for key, item in value.items()
    }
    if normalized.get("field") != "row_key":
        return normalized
    condition = normalized.get("condition")
    if not isinstance(condition, dict) or condition.get("filterType") != "set":
        return normalized
    values = condition.get("values")
    if not isinstance(values, list):
        return normalized

    prefix = f"{source_dataset_id}::"
    condition["values"] = [
        row_key[len(prefix) :]
        for row_key in values
        if isinstance(row_key, str) and row_key.startswith(prefix)
    ]
    return normalized


def _normalize_collection_sample_ids(
    sample_ids: list[str],
    *,
    source_dataset_id: str,
) -> list[str]:
    prefix = f"{source_dataset_id}::"
    return [
        sample_id[len(prefix) :]
        for sample_id in sample_ids
        if sample_id.startswith(prefix)
    ]


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
        collection_member_ids: list[str] | None = None,
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
            report = await self._collection_readiness(
                source.identity,
                revision,
                org_id=org_id,
                collection_member_ids=collection_member_ids,
                sample_ids=sample_ids,
                sample_filter=sample_filter,
            )
        if not report.ready:
            raise TrainingReadinessError(report)
        return report

    async def _collection_readiness(
        self,
        source_identity: str,
        revision: DatasetCollectionRevision,
        *,
        org_id: str,
        collection_member_ids: list[str] | None,
        sample_ids: list[str] | None,
        sample_filter: dict[str, Any] | None,
    ) -> TrainingReadinessReport:
        member_by_id: dict[str, str] = {}
        for member in revision.members:
            member_id = member.get("member_id")
            dataset_id = member.get("source_dataset_id")
            if not isinstance(member_id, str) or not isinstance(dataset_id, str):
                raise ValueError(
                    f"Collection revision '{revision.id}' has invalid member identity"
                )
            member_by_id[member_id] = dataset_id
        selected_ids = (
            tuple(member_by_id)
            if collection_member_ids is None
            else tuple(collection_member_ids)
        )
        if not selected_ids or len(selected_ids) != len(set(selected_ids)):
            raise ValueError("collection_member_ids must be non-empty and unique")
        missing = [
            member_id for member_id in selected_ids if member_id not in member_by_id
        ]
        if missing:
            raise ValueError(
                "Collection revision does not contain selected members: "
                + ", ".join(missing)
            )
        datasets = await asyncio.gather(
            *(
                self._dataset_reader.get_dataset(member_by_id[member_id], org_id=org_id)
                for member_id in selected_ids
            )
        )
        if any(dataset is None for dataset in datasets):
            missing_datasets = [
                member_by_id[member_id]
                for member_id, dataset in zip(selected_ids, datasets, strict=True)
                if dataset is None
            ]
            raise TrainingDatasetNotFoundError(",".join(missing_datasets))
        reports = await asyncio.gather(
            *(
                self._readiness.assess_classes(
                    dataset=dataset,
                    sample_ids=(
                        _normalize_collection_sample_ids(
                            sample_ids,
                            source_dataset_id=member_by_id[member_id],
                        )
                        if sample_ids is not None
                        else None
                    ),
                    sample_filter=(
                        _normalize_collection_row_keys(
                            sample_filter,
                            source_dataset_id=member_by_id[member_id],
                        )
                        if sample_filter is not None
                        else None
                    ),
                )
                for member_id, dataset in zip(selected_ids, datasets, strict=True)
                if dataset is not None
            )
        )
        label_counts: dict[str, int] = {}
        for report in reports:
            for label, count in report.label_counts.items():
                label_counts[label] = label_counts.get(label, 0) + count
        active_labels = sorted(
            label for label, count in label_counts.items() if count > 0
        )
        reasons = (
            ()
            if len(active_labels) >= 2
            else (f"training requires at least 2 active labels; got {active_labels}",)
        )
        return TrainingReadinessReport(
            dataset_id=source_identity,
            annotated_samples=sum(report.annotated_samples for report in reports),
            readable_samples=sum(report.readable_samples for report in reports),
            runtime_resolvable_samples=sum(
                report.runtime_resolvable_samples for report in reports
            ),
            unusable_samples=sum(report.unusable_samples for report in reports),
            skipped_samples=sum(report.skipped_samples for report in reports),
            label_counts=label_counts,
            failure_reasons=reasons,
        )
