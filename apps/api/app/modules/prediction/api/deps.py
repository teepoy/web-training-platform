from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from omegaconf import DictConfig  # pyright: ignore[reportMissingImports, reportMissingModuleSource]

from app.modules.datasets.application.sample_access.factory import SampleAccessFactory
from app.modules.datasets.application.services.feature_ops import FeatureOpsService
from app.modules.prediction.application.services.prediction_orchestrator import (
    PredictionOrchestrator,
)
from app.modules.prediction.application.services.prediction_service import (
    PredictionService,
)
from app.modules.prediction.domain.repository import PredictionRepository
from app.shared.application.artifacts import ArtifactService
from app.shared.db.sql_repository import SqlRepository
from app.shared.domain.protocols import (
    ArtifactStorage,
    EmbeddingClient,
    GpuWorker,
    InferenceWorker,
    LlmClient,
    PrefectClient,
)


def get_config(request: Request) -> DictConfig:
    return request.app.state.container.config


def get_prediction_repository(request: Request) -> PredictionRepository:
    return request.app.state.container.prediction_repository


def get_sql_repository(request: Request) -> SqlRepository:
    repository = request.app.state.container.prediction_repository
    if not isinstance(repository, SqlRepository):
        raise TypeError("Prediction repository is not a SqlRepository")
    return repository


def get_artifact_storage(request: Request) -> ArtifactStorage:
    return request.app.state.container.artifact_storage


def get_embedding_client(request: Request) -> EmbeddingClient:
    return request.app.state.container.embedding_client


def get_llm_client(request: Request) -> LlmClient:
    return request.app.state.container.llm_client


def get_inference_worker(request: Request) -> InferenceWorker:
    return request.app.state.container.inference_worker


def get_gpu_worker(request: Request) -> GpuWorker:
    return request.app.state.container.gpu_worker


def get_prefect_client(request: Request) -> PrefectClient:
    return request.app.state.container.prefect_client


def get_sample_access_factory(
    repository: Annotated[SqlRepository, Depends(get_sql_repository)],
) -> SampleAccessFactory:
    return SampleAccessFactory(repo=repository)


def get_feature_ops_service(
    repository: Annotated[SqlRepository, Depends(get_sql_repository)],
    embedding_client: Annotated[EmbeddingClient, Depends(get_embedding_client)],
    inference_worker: Annotated[InferenceWorker, Depends(get_inference_worker)],
    gpu_worker: Annotated[GpuWorker, Depends(get_gpu_worker)],
) -> FeatureOpsService:
    return FeatureOpsService(
        repository=repository,
        embedding_service=embedding_client,
        inference_worker=inference_worker,
        gpu_worker=gpu_worker,
    )


def get_artifact_service(
    storage: Annotated[ArtifactStorage, Depends(get_artifact_storage)],
    repository: Annotated[SqlRepository, Depends(get_sql_repository)],
) -> ArtifactService:
    return ArtifactService(storage=storage, repository=repository)


def get_prediction_service(
    repository: Annotated[PredictionRepository, Depends(get_prediction_repository)],
    artifact_storage: Annotated[ArtifactStorage, Depends(get_artifact_storage)],
    config: Annotated[DictConfig, Depends(get_config)],
    embedding_client: Annotated[EmbeddingClient, Depends(get_embedding_client)],
    llm_client: Annotated[LlmClient, Depends(get_llm_client)],
    inference_worker: Annotated[InferenceWorker, Depends(get_inference_worker)],
    gpu_worker: Annotated[GpuWorker, Depends(get_gpu_worker)],
) -> PredictionService:
    return PredictionService(
        repository=repository,
        artifact_storage=artifact_storage,
        config=config,
        embedding_client=embedding_client,
        llm_client=llm_client,
        inference_worker=inference_worker,
        gpu_worker=gpu_worker,
    )


def get_prediction_orchestrator(
    prefect_client: Annotated[PrefectClient, Depends(get_prefect_client)],
    repository: Annotated[PredictionRepository, Depends(get_prediction_repository)],
) -> PredictionOrchestrator:
    return PredictionOrchestrator(
        prefect_client=prefect_client,
        repository=repository,
    )


ConfigDep = Annotated[DictConfig, Depends(get_config)]
PredictionRepositoryDep = Annotated[
    PredictionRepository,
    Depends(get_prediction_repository),
]
SqlRepositoryDep = Annotated[SqlRepository, Depends(get_sql_repository)]
ArtifactStorageDep = Annotated[ArtifactStorage, Depends(get_artifact_storage)]
SampleAccessFactoryDep = Annotated[
    SampleAccessFactory,
    Depends(get_sample_access_factory),
]
FeatureOpsServiceDep = Annotated[
    FeatureOpsService,
    Depends(get_feature_ops_service),
]
ArtifactServiceDep = Annotated[ArtifactService, Depends(get_artifact_service)]
PredictionServiceDep = Annotated[PredictionService, Depends(get_prediction_service)]
PredictionOrchestratorDep = Annotated[
    PredictionOrchestrator,
    Depends(get_prediction_orchestrator),
]
