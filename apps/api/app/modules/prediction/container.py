from __future__ import annotations

from dataclasses import dataclass

from injector import Module, inject, provider, singleton

from app.modules.dataset_collections.port.local import (
    DatasetCollectionRevisionReaderPort,
)
from app.modules.datasets.port.dataset_reader import DatasetReader
from app.modules.datasets.port.local import IDatasetService
from app.modules.models.port.local import ModelCatalogPort
from app.modules.prediction.adapter.repositories.repository import (
    PredictionRepository as SqlPredictionRepository,
)
from app.modules.runtime.port.local import RuntimeRoutingPort
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.shared.context import SharedInfra
from app.modules.prediction.app.services.submission_service import (
    PredictionSubmissionService,
)
from app.modules.prediction.app.services.prediction_query import PredictionQueryService
from app.modules.prediction.app.services.prediction_review import (
    PredictionReviewService,
)
from app.modules.prediction.app.services.prediction_runtime import (
    PredictionRuntimeService,
)
from app.modules.prediction.domain.repository import PredictionRepository
from app.modules.prediction.port.local import (
    PredictionDatasetUsagePort,
    PredictionCollectionPort,
    PredictionExecutionPort,
    PredictionQueryPort,
    PredictionReviewPort,
    PredictionRuntimePort,
)


@dataclass
class PredictionContext:
    prediction_repository: PredictionRepository
    prediction_runtime_service: PredictionRuntimeService
    prediction_query_service: PredictionQueryService
    prediction_review_service: PredictionReviewService
    prediction_submission: PredictionSubmissionService
    dataset_service: IDatasetService
    dataset_storage_factory: DatasetStorageFactoryPort


def init_prediction(
    shared: SharedInfra,
    dataset_service: IDatasetService,
    dataset_reader: DatasetReader,
    model_catalog: ModelCatalogPort,
    dataset_storage_factory: DatasetStorageFactoryPort,
    runtime_router: RuntimeRoutingPort,
    collection_revisions: DatasetCollectionRevisionReaderPort,
) -> PredictionContext:
    prediction_repository = SqlPredictionRepository(
        session_factory=shared.session_factory.sessionmaker
    )
    runtime_service = PredictionRuntimeService(
        dataset_reader=dataset_reader,
        model_catalog=model_catalog,
        runtime_router=runtime_router,
    )
    query_service = PredictionQueryService(
        repository=prediction_repository,
        dataset_storage_factory=dataset_storage_factory,
        dataset_reader=dataset_reader,
    )
    review_service = PredictionReviewService(
        repository=prediction_repository,
        config=shared.config,
        dataset_storage_factory=dataset_storage_factory,
        dataset_reader=dataset_reader,
        model_catalog=model_catalog,
    )
    submission = PredictionSubmissionService(
        prefect_client=shared.prefect_client,
        repository=prediction_repository,
        runtime_router=runtime_router,
        dataset_reader=dataset_reader,
        model_catalog=model_catalog,
        collection_revisions=collection_revisions,
    )
    return PredictionContext(
        prediction_repository=prediction_repository,
        prediction_runtime_service=runtime_service,
        prediction_query_service=query_service,
        prediction_review_service=review_service,
        prediction_submission=submission,
        dataset_service=dataset_service,
        dataset_storage_factory=dataset_storage_factory,
    )


class PredictionModule(Module):
    @inject
    @provider
    @singleton
    def provide_prediction_context(
        self,
        shared: SharedInfra,
        dataset_service: IDatasetService,
        dataset_reader: DatasetReader,
        model_catalog: ModelCatalogPort,
        dataset_storage_factory: DatasetStorageFactoryPort,
        runtime_router: RuntimeRoutingPort,
        collection_revisions: DatasetCollectionRevisionReaderPort,
    ) -> PredictionContext:
        return init_prediction(
            shared,
            dataset_service=dataset_service,
            dataset_reader=dataset_reader,
            model_catalog=model_catalog,
            dataset_storage_factory=dataset_storage_factory,
            runtime_router=runtime_router,
            collection_revisions=collection_revisions,
        )

    @provider
    @singleton
    def provide_prediction_repository(
        self, context: PredictionContext
    ) -> PredictionRepository:
        return context.prediction_repository

    @provider
    @singleton
    def provide_prediction_dataset_usage(
        self, context: PredictionContext
    ) -> PredictionDatasetUsagePort:
        return context.prediction_repository

    @provider
    @singleton
    def provide_prediction_runtime_service(
        self, context: PredictionContext
    ) -> PredictionRuntimeService:
        return context.prediction_runtime_service

    @provider
    @singleton
    def provide_prediction_query_service(
        self, context: PredictionContext
    ) -> PredictionQueryService:
        return context.prediction_query_service

    @provider
    @singleton
    def provide_prediction_review_service(
        self, context: PredictionContext
    ) -> PredictionReviewService:
        return context.prediction_review_service

    @provider
    @singleton
    def provide_prediction_submission(
        self, context: PredictionContext
    ) -> PredictionSubmissionService:
        return context.prediction_submission

    @provider
    @singleton
    def provide_prediction_runtime(
        self, context: PredictionContext
    ) -> PredictionRuntimePort:
        return context.prediction_runtime_service

    @provider
    @singleton
    def provide_prediction_query(
        self, context: PredictionContext
    ) -> PredictionQueryPort:
        return context.prediction_query_service

    @provider
    @singleton
    def provide_prediction_review(
        self, context: PredictionContext
    ) -> PredictionReviewPort:
        return context.prediction_review_service

    @provider
    @singleton
    def provide_prediction_collection(
        self, context: PredictionContext
    ) -> PredictionCollectionPort:
        return context.prediction_review_service

    @provider
    @singleton
    def provide_prediction_execution(
        self, context: PredictionContext
    ) -> PredictionExecutionPort:
        return context.prediction_submission
