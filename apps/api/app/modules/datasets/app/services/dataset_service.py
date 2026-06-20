from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from omegaconf import DictConfig
from platform_runtime.sparse import DatasetPayloadStore

from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.modules.datasets.domain.repository import DatasetRepository
from app.shared.api.schemas import (
    Annotation,
    Dataset,
    DatasetStorageMode,
    SPARSE_NO_LS,
)
from app.shared.domain.protocols import ArtifactStorage, LabelStudioClient
from app.shared.infrastructure.label_studio.client import ls_annotation_to_platform
from app.shared.infrastructure.label_studio.read_repository import LsReadRepository


class DatasetService:
    def __init__(
        self,
        repository: DatasetRepository,
        storage_factory: DatasetStorageFactory,
        ls_client: LabelStudioClient,
        storage: ArtifactStorage,
        payload_store: DatasetPayloadStore,
        capability_guard: Callable[[Dataset], None],
        config: DictConfig,
    ) -> None:
        self._repository = repository
        self._storage_factory = storage_factory
        self._ls_client = ls_client
        self._storage = storage
        self._payload_store = payload_store
        self._capability_guard = capability_guard
        self._config = config

    def to_response(self, dataset: Dataset) -> Dataset:
        """Compute response-only dataset fields such as LS URL."""
        if dataset.ls_project_id == SPARSE_NO_LS:
            return dataset

        ls_url = str(
            self._config.label_studio.external_url or self._config.label_studio.url
        ).rstrip("/")
        if dataset.ls_project_id and ls_url:
            return dataset.model_copy(
                update={"ls_project_url": f"{ls_url}/projects/{dataset.ls_project_id}"}
            )
        return dataset

    async def to_list_response(self, dataset: Dataset) -> Dataset:
        """Compute lightweight fields used by the dataset index."""
        sample_count = await self._resolve_sample_count(dataset)
        dataset_meta = dict(dataset.dataset_meta or {})
        dataset_meta.update(
            {"sample_count": sample_count, "total_samples": sample_count}
        )
        return self.to_response(
            dataset.model_copy(update={"dataset_meta": dataset_meta})
        )

    async def _resolve_sample_count(self, dataset: Dataset) -> int:
        if dataset.storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE:
            try:
                manifest = await self._payload_store.get_manifest(
                    dataset.id,
                    dataset.org_id or "",
                )
            except (FileNotFoundError, KeyError):
                return 0
            return int(manifest.total_rows)

        storage = await self._storage_factory.open(dataset.id, dataset.org_id)
        stats = await storage.get_annotation_stats()
        return int(stats.get("total_samples", 0))

    async def build_export_data(
        self,
        dataset_id: str,
        ls_read_repository: LsReadRepository,
    ):
        """Return (dataset, samples, annotations) sourced from Label Studio read DB."""
        repo = self._repository
        dataset = await repo.get_dataset(dataset_id)
        if dataset is None:
            raise HTTPException(status_code=404, detail="dataset not found")

        if not dataset.ls_project_id or dataset.ls_project_id == SPARSE_NO_LS:
            raise HTTPException(
                status_code=500,
                detail="Dataset has no Label Studio project — cannot export.",
            )

        try:
            storage = await self._storage_factory.open(
                dataset_id, org_id=dataset.org_id or ""
            )
            all_samples, _ = await storage.list_samples(limit=100_000)
            task_id_to_sample: dict[int, Any] = {}
            for s in all_samples:
                if hasattr(s, "ls_task_id") and s.ls_task_id is not None:
                    task_id_to_sample[s.ls_task_id] = s

            ls_tasks = await ls_read_repository.get_tasks_for_project(
                int(dataset.ls_project_id)
            )
            task_ids = [t["id"] for t in ls_tasks]
            ls_annotations = (
                await ls_read_repository.get_annotations_for_tasks(task_ids)
                if task_ids
                else {}
            )

            samples_out: list[Any] = []
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

    async def merge_label_space(
        self, dataset_id: str, incoming_labels: set[str]
    ) -> bool:
        """Merge new labels into the dataset's task_spec.label_space.

        Returns True if label_space was expanded, False if no-op.
        """
        if not incoming_labels:
            return False

        # Filter out falsy labels (None, empty string)
        incoming_labels = {label for label in incoming_labels if label}
        if not incoming_labels:
            return False

        dataset = await self._repository.get_dataset(dataset_id)
        if dataset is None:
            return False

        existing = set(dataset.task_spec.label_space)
        new_labels = incoming_labels - existing
        if not new_labels:
            return False

        merged = sorted(existing | incoming_labels)
        updated = dataset.task_spec.model_copy(update={"label_space": merged})
        await self._repository.update_dataset_meta(
            dataset_id, updated.model_dump(mode="json")
        )
        return True
