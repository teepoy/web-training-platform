from __future__ import annotations

from app.modules.dataset_collections.port.local import CollectionDatasetUsagePort
from app.modules.prediction.port.local import PredictionDatasetUsagePort
from app.modules.training.port.local import TrainingDatasetUsagePort


class DatasetDeletionConflictError(Exception):
    def __init__(self, active_job_types: list[str]) -> None:
        self.active_job_types = active_job_types
        joined = " and ".join(active_job_types)
        super().__init__(
            f"Dataset cannot be deleted while {joined} jobs are queued or running"
        )


class DatasetDeletionGuard:
    def __init__(
        self,
        *,
        training_usage: TrainingDatasetUsagePort,
        prediction_usage: PredictionDatasetUsagePort,
        collection_usage: CollectionDatasetUsagePort,
    ) -> None:
        self._training_usage = training_usage
        self._prediction_usage = prediction_usage
        self._collection_usage = collection_usage

    async def ensure_deletable(self, *, dataset_id: str, org_id: str) -> None:
        active_job_types: list[str] = []
        if await self._training_usage.has_active_jobs(
            dataset_id=dataset_id, org_id=org_id
        ):
            active_job_types.append("training")
        if await self._prediction_usage.has_active_jobs(
            dataset_id=dataset_id, org_id=org_id
        ):
            active_job_types.append("prediction")
        if await self._collection_usage.has_dataset_references(dataset_id, org_id):
            active_job_types.append("dataset collection")
        if active_job_types:
            raise DatasetDeletionConflictError(active_job_types)
