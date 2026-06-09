from __future__ import annotations

from dataclasses import dataclass

from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.modules.datasets.port.local import IDatasetService
from app.shared.context import SharedInfra
from app.shared.db.sql_repository import SqlRepository
from app.modules.prediction.app.services.batch_lookup import BatchPredictionService
from app.modules.prediction.app.services.prediction_orchestrator import (
    PredictionOrchestrator,
)


@dataclass
class PredictionContext:
    prediction_repository: SqlRepository
    prediction_orchestrator: PredictionOrchestrator
    batch_prediction: BatchPredictionService
    dataset_service: IDatasetService
    dataset_storage_factory: DatasetStorageFactory


def init_prediction(
    shared: SharedInfra,
    dataset_service: IDatasetService,
    dataset_storage_factory: DatasetStorageFactory,
) -> PredictionContext:
    prediction_repository = SqlRepository(session_factory=shared.session_factory)
    orchestrator = PredictionOrchestrator(
        prefect_client=shared.prefect_client,
        repository=prediction_repository,
    )
    batch_prediction = BatchPredictionService(repository=prediction_repository)
    return PredictionContext(
        prediction_repository=prediction_repository,
        prediction_orchestrator=orchestrator,
        batch_prediction=batch_prediction,
        dataset_service=dataset_service,
        dataset_storage_factory=dataset_storage_factory,
    )
