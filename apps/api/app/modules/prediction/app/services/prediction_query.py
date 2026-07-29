from __future__ import annotations

from injector import inject

from app.modules.datasets.port.dataset_reader import DatasetReader
from app.modules.prediction.domain.repository import PredictionRepository
from app.modules.prediction.domain.results import PredictionResult
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.shared.api.schemas import PlatformPrediction


class PredictionQueryService:
    """Read persisted prediction results through the owning storage boundary."""

    @inject
    def __init__(
        self,
        repository: PredictionRepository,
        dataset_storage_factory: DatasetStorageFactoryPort,
        dataset_reader: DatasetReader,
    ) -> None:
        self._repository = repository
        self._dataset_storage_factory = dataset_storage_factory
        self._dataset_reader = dataset_reader

    @staticmethod
    def _result_from_prediction(prediction: PlatformPrediction) -> PredictionResult:
        return PredictionResult(
            id=prediction.id,
            sample_id=prediction.sample_id,
            predicted_label=prediction.predicted_label,
            confidence=prediction.confidence,
            all_scores=prediction.all_scores,
            model_id=prediction.model_id,
            target=prediction.target,
            model_version=prediction.model_version,
            job_id=prediction.job_id,
            created_at=prediction.created_at,
            error=prediction.error,
        )

    async def list_predictions_for_sample(
        self,
        *,
        sample_id: str,
        org_id: str,
        dataset_id: str | None = None,
        model_version: str | None = None,
    ) -> list[PredictionResult]:
        if dataset_id is not None:
            dataset = await self._dataset_reader.get_dataset(dataset_id, org_id)
            if dataset is None:
                raise ValueError(f"Dataset not found: {dataset_id}")
            storage = await self._dataset_storage_factory.open(dataset_id, org_id)
            sample = await storage.get_sample(sample_id)
        else:
            sample = await self._dataset_reader.get_sample(sample_id)
        if sample is None:
            raise ValueError(f"Sample not found: {sample_id}")

        predictions = await self._repository.list_platform_predictions_for_sample(
            sample_id=sample_id,
            org_id=org_id,
            model_version=model_version,
        )
        return [self._result_from_prediction(item) for item in predictions]

    async def list_predictions_for_job(
        self,
        job_id: str,
        org_id: str,
        offset: int = 0,
        limit: int = 1000,
    ) -> list[PredictionResult]:
        job = await self._repository.get_prediction_job(job_id, org_id)
        if job is None:
            raise ValueError(f"Prediction job not found: {job_id}")
        dataset = await self._dataset_reader.get_dataset(job.dataset_id, org_id)
        if dataset is None:
            raise ValueError(f"Dataset not found: {job.dataset_id}")
        storage = await self._dataset_storage_factory.open(job.dataset_id, org_id)
        return await storage.list_predictions(
            job_id=job_id,
            offset=offset,
            limit=limit,
        )
