from __future__ import annotations

from fastapi import HTTPException

from app.shared.api.schemas import Annotation, Sample, SPARSE_NO_LS
from app.modules.datasets.application.sample_access.factory import SampleAccessFactory
from app.shared.infrastructure.label_studio.read_repository import LsReadRepository
from app.shared.db.sql_repository import SqlRepository
from app.shared.infrastructure.label_studio.client import ls_annotation_to_platform


class DatasetService:
    def __init__(
        self,
        repository: SqlRepository,
        sample_factory: SampleAccessFactory,
        ls_read_repository: LsReadRepository,
    ) -> None:
        self._repository = repository
        self._sample_factory = sample_factory
        self._ls_read_repository = ls_read_repository

    async def build_export_data(self, dataset_id: str):
        """Return (dataset, samples, annotations) sourced from Label Studio read DB."""
        repo = self._repository
        dataset = await repo.get_dataset(dataset_id)
        if dataset is None:
            raise HTTPException(status_code=404, detail="dataset not found")

        access = self._sample_factory.create(dataset.storage_mode)

        if not dataset.ls_project_id or dataset.ls_project_id == SPARSE_NO_LS:
            raise HTTPException(
                status_code=500,
                detail="Dataset has no Label Studio project — cannot export.",
            )

        try:
            all_samples, _ = await access.list_samples(dataset_id, limit=100_000)
            task_id_to_sample: dict[int, Sample] = {
                s.ls_task_id: s for s in all_samples if s.ls_task_id is not None
            }

            ls_tasks = await self._ls_read_repository.get_tasks_for_project(
                int(dataset.ls_project_id)
            )
            task_ids = [t["id"] for t in ls_tasks]
            ls_annotations = (
                await self._ls_read_repository.get_annotations_for_tasks(task_ids)
                if task_ids
                else {}
            )

            samples_out: list[Sample] = []
            annotations_out: list[Annotation] = []

            for ls_task in ls_tasks:
                task_id = ls_task["id"]
                platform_sample = task_id_to_sample.get(task_id)
                if platform_sample is None:
                    continue
                samples_out.append(platform_sample)

                for ls_ann in ls_annotations.get(task_id, []):
                    result = ls_ann.get("result", [])
                    label = ls_annotation_to_platform(result)
                    if label:
                        annotations_out.append(
                            Annotation(
                                sample_id=platform_sample.id,
                                label=label,
                                created_by="label_studio",
                            )
                        )

            return dataset, samples_out, annotations_out

        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Label Studio database read failed: {exc}"
            )
