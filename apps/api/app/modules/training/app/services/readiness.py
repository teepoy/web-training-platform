from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any, cast

from injector import inject

from app.modules.sc.app.services.sample_filter import (
    parse_and_apply_workflow_sample_filter,
)
from app.modules.sc.app.services.training_images import (
    resolve_sc_training_image_bytes,
    row_has_readable_training_images,
    row_has_runtime_resolvable_training_images,
)
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.modules.training.domain.readiness import TrainingReadinessReport
from app.shared.api.schemas import Dataset
from app.shared.domain.protocols import ArtifactStorage

_READINESS_BATCH_SIZE = 64


class TrainingReadinessService:
    @inject
    def __init__(
        self,
        storage_factory: DatasetStorageFactoryPort,
        artifact_storage: ArtifactStorage,
    ) -> None:
        self._storage_factory = storage_factory
        self._artifact_storage = artifact_storage

    async def assess_classes(
        self,
        *,
        dataset: Dataset,
        sample_ids: list[str] | None = None,
        sample_filter: dict[str, Any] | None = None,
    ) -> TrainingReadinessReport:
        annotated, label_column = await self._annotated_frame(
            dataset=dataset,
            sample_ids=sample_ids,
            sample_filter=sample_filter,
        )
        label_counts = await asyncio.to_thread(
            self._collect_label_counts,
            annotated,
            label_column,
        )
        annotated_samples = sum(label_counts.values())
        active_labels = sorted(label_counts)
        reasons: list[str] = []
        if not annotated_samples:
            reasons.append("dataset has no annotated samples in the selected scope")
        if len(active_labels) < 2:
            reasons.append(
                f"training requires at least 2 active labels; got {active_labels}"
            )
        return TrainingReadinessReport(
            dataset_id=dataset.id,
            annotated_samples=annotated_samples,
            readable_samples=annotated_samples,
            runtime_resolvable_samples=0,
            unusable_samples=0,
            skipped_samples=0,
            label_counts=label_counts,
            failure_reasons=tuple(reasons),
        )

    async def assess(
        self,
        *,
        dataset: Dataset,
        sample_ids: list[str] | None,
        sample_filter: dict[str, Any] | None,
    ) -> TrainingReadinessReport:
        if dataset.dataset_type != "image_sc":
            return await self.assess_classes(
                dataset=dataset,
                sample_ids=sample_ids,
                sample_filter=sample_filter,
            )

        annotated, label_column = await self._annotated_frame(
            dataset=dataset,
            sample_ids=sample_ids,
            sample_filter=sample_filter,
        )
        if annotated is None or label_column is None:
            annotated_batches: Iterable[Any] = ()
        else:
            annotated_batches = annotated.collect_batches(
                chunk_size=_READINESS_BATCH_SIZE,
                maintain_order=False,
            )

        annotated_samples = 0
        readable_samples = 0
        runtime_resolvable_samples = 0
        unusable_samples = 0
        label_counts: dict[str, int] = {}

        for batch in annotated_batches:
            assert label_column is not None
            raw_rows = [dict(row) for row in batch.iter_rows(named=True)]
            annotated_samples += len(raw_rows)
            rows = await asyncio.gather(
                *(
                    resolve_sc_training_image_bytes(
                        raw_row,
                        self._artifact_storage,
                    )
                    for raw_row in raw_rows
                )
            )
            for row in rows:
                label = str(row.get(label_column) or "").strip()
                if row_has_readable_training_images(row):
                    readable_samples += 1
                    label_counts[label] = label_counts.get(label, 0) + 1
                elif row_has_runtime_resolvable_training_images(row):
                    runtime_resolvable_samples += 1
                    label_counts[label] = label_counts.get(label, 0) + 1
                else:
                    unusable_samples += 1

        reasons: list[str] = []
        if not annotated_samples:
            reasons.append("dataset has no annotated samples in the selected scope")
        active_labels = sorted(
            label for label, count in label_counts.items() if count > 0
        )
        if len(active_labels) < 2:
            reasons.append(
                "training requires at least 2 active labels after image validation; "
                f"got {active_labels}"
            )

        return TrainingReadinessReport(
            dataset_id=dataset.id,
            annotated_samples=annotated_samples,
            readable_samples=readable_samples,
            runtime_resolvable_samples=runtime_resolvable_samples,
            unusable_samples=unusable_samples,
            skipped_samples=unusable_samples,
            label_counts=label_counts,
            failure_reasons=tuple(reasons),
        )

    async def _annotated_frame(
        self,
        *,
        dataset: Dataset,
        sample_ids: list[str] | None,
        sample_filter: dict[str, Any] | None,
    ) -> tuple[Any | None, str | None]:
        if not dataset.org_id:
            raise ValueError(
                f"Dataset is missing required organization ownership: {dataset.id}"
            )
        storage = await self._storage_factory.open_from_metadata(
            dataset,
            org_id=dataset.org_id,
        )
        lazyframe = await storage.list_samples(
            with_labels=True,
            with_predictions=sample_filter is not None,
            return_lazyframe=True,
            sample_ids=sample_ids,
        )
        if sample_filter is not None:
            lazyframe = parse_and_apply_workflow_sample_filter(
                cast(Any, lazyframe),
                sample_filter,
            )

        import polars as pl

        schema_names = await asyncio.to_thread(self._schema_names, lazyframe)
        label_column = (
            "label"
            if "label" in schema_names
            else "latest_label"
            if "latest_label" in schema_names
            else None
        )
        annotated = None
        if label_column is not None:
            annotated = cast(Any, lazyframe).filter(
                pl.col(label_column).is_not_null()
                & (pl.col(label_column).cast(pl.Utf8).str.strip_chars() != "")
            )
        return annotated, label_column

    @staticmethod
    def _schema_names(lazyframe: Any) -> set[str]:
        return set(cast(Any, lazyframe).collect_schema().names())

    @staticmethod
    def _collect_label_counts(
        annotated: Any | None,
        label_column: str | None,
    ) -> dict[str, int]:
        if annotated is None or label_column is None:
            return {}
        import polars as pl

        label = pl.col(label_column).cast(pl.Utf8).str.strip_chars().alias("label")
        rows = (
            cast(Any, annotated)
            .select(label)
            .group_by("label")
            .agg(pl.len().alias("count"))
            .collect()
            .iter_rows(named=True)
        )
        return {str(row["label"]): int(row["count"]) for row in rows}
