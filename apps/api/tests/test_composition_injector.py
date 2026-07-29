from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import Request
import pytest

from app.composition import (
    build_app_context,
    build_flow_app_context,
    close_flow_app_context,
)
from app.core.config import load_config
from app.modules.storage.port.local import DataPlaneSchemaRegistryPort
from app.modules.agent.port.http import deps as agent_deps
from app.modules.dashboard.port.http import deps as dashboard_deps
from app.modules.datasets.domain.repository import DatasetRepository
from app.modules.datasets.port.http import deps as dataset_deps
from app.modules.datasets.port.local import (
    IDatasetService,
    SampleSimilarityPort,
)
from app.modules.sc.materialization.port.local import ScInspectionMaterializerPort
from app.modules.models.port.local import ModelCatalogPort
from app.modules.prediction.port.local import (
    PredictionCollectionPort,
    PredictionExecutionPort,
    PredictionQueryPort,
    PredictionReviewPort,
    PredictionRuntimePort,
)
from app.modules.prediction.app.services.prediction_orchestrator import (
    PredictionOrchestrator,
)
from app.modules.prediction.app.services.prediction_query import PredictionQueryService
from app.modules.prediction.app.services.prediction_review import (
    PredictionReviewService,
)
from app.modules.prediction.app.services.prediction_runtime import (
    PredictionRuntimeService,
)
from app.modules.runtime.port.local import RuntimeRoutingPort
from app.modules.jobs.schedules.port.local import ScheduleManagementPort
from app.modules.models.port.http import deps as model_deps
from app.modules.models.app.services.model_service import ModelService
from app.modules.sc.domain.image_fetcher import ScImageFetcher
from app.modules.sc.port.http import deps as sc_deps
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.modules.jobs.task_tracker.port.task_tracker_port import TaskTrackerPort
from app.modules.training.domain.repository import TrainingRepository
from app.modules.training.port.local import TrainingExecutionPort
from app.modules.training.app.services.orchestrator import TrainingOrchestrator
from app.modules.training.port.http import deps as training_deps
from app.shared.context import SharedInfra


@pytest.mark.asyncio
async def test_flow_context_owns_redis_event_publisher() -> None:
    redis = MagicMock()
    redis.aclose = AsyncMock()

    with patch("redis.asyncio.Redis", return_value=redis):
        ctx = build_flow_app_context(load_config(skip_runtime_validation=True))

    publisher = ctx.shared.redis_event_publisher
    assert publisher is not None
    await close_flow_app_context(ctx)
    redis.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_app_context_injector_binds_existing_instances() -> None:
    ctx = build_app_context(load_config(skip_runtime_validation=True))
    try:
        injector = ctx.injector
        assert injector is not None
        assert ctx.datasets is not None
        assert ctx.jobs is not None
        assert ctx.training is not None
        assert ctx.prediction is not None
        assert ctx.models is not None
        assert ctx.jobs.schedules is not None
        assert ctx.runtime is not None
        assert ctx.storage is not None
        assert ctx.sc is not None

        assert injector.get(SharedInfra) is ctx.shared
        assert injector.get(IDatasetService) is ctx.datasets.dataset_service
        assert (
            injector.get(SampleSimilarityPort)
            is ctx.datasets.sample_similarity_service
        )
        assert (
            injector.get(DatasetStorageFactoryPort)
            is ctx.storage.dataset_storage_factory
        )
        assert injector.get(DatasetRepository) is ctx.datasets.dataset_repository
        assert injector.get(TaskTrackerPort) is ctx.jobs.task_tracker.task_tracker_port
        assert ctx.jobs.task_tracker.task_tracker_port is ctx.training.repository
        assert injector.get(TrainingRepository) is ctx.training.repository
        assert (
            injector.get(TrainingExecutionPort)
            is injector.get(TrainingOrchestrator)
        )
        assert (
            injector.get(PredictionExecutionPort)
            is ctx.prediction.prediction_orchestrator
        )
        assert (
            injector.get(PredictionOrchestrator)
            is ctx.prediction.prediction_orchestrator
        )
        assert (
            injector.get(PredictionRuntimeService)
            is ctx.prediction.prediction_runtime_service
        )
        assert (
            injector.get(PredictionQueryService)
            is ctx.prediction.prediction_query_service
        )
        assert (
            injector.get(PredictionReviewService)
            is ctx.prediction.prediction_review_service
        )
        assert (
            injector.get(PredictionRuntimePort)
            is ctx.prediction.prediction_runtime_service
        )
        assert (
            injector.get(PredictionQueryPort)
            is ctx.prediction.prediction_query_service
        )
        assert (
            injector.get(PredictionCollectionPort)
            is ctx.prediction.prediction_review_service
        )
        assert (
            injector.get(PredictionReviewPort)
            is ctx.prediction.prediction_review_service
        )
        assert injector.get(ModelCatalogPort) is ctx.models.model_repository
        assert isinstance(injector.get(ModelService), ModelService)
        assert (
            injector.get(ScheduleManagementPort)
            is ctx.jobs.schedules.scheduler_service
        )
        assert injector.get(RuntimeRoutingPort) is ctx.runtime.routing_service
        assert (
            injector.get(DataPlaneSchemaRegistryPort)
            is ctx.storage.schema_registry
        )
        assert (
            injector.get(ScInspectionMaterializerPort)
            is ctx.sc.sc_inspection_materializer
        )
        assert injector.get(ScImageFetcher) is ctx.sc.image_fetcher
    finally:
        await close_flow_app_context(ctx)


@pytest.mark.asyncio
async def test_migrated_http_deps_resolve_from_injector() -> None:
    ctx = build_app_context(load_config(skip_runtime_validation=True))
    request = cast(
        Request,
        SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(app_context=ctx))),
    )
    try:
        injector = ctx.injector
        assert injector is not None
        assert ctx.datasets is not None
        assert ctx.agent is not None
        assert ctx.dashboard is not None
        assert ctx.models is not None
        assert ctx.jobs is not None
        assert ctx.training is not None
        assert ctx.sc is not None

        assert agent_deps.get_session_store(request) is ctx.agent.session_store
        assert agent_deps.get_model_service(request) is ctx.models.model_repository
        assert (
            agent_deps.get_orchestrator(request)
            is injector.get(TrainingOrchestrator)
        )
        assert dataset_deps.get_repository(request) is ctx.datasets.dataset_repository
        assert dataset_deps.get_dataset_service(request) is ctx.datasets.dataset_service
        assert dashboard_deps.get_repository(request) is ctx.dashboard.task_tracker_port
        assert model_deps.get_model_service(request) is injector.get(ModelService)
        assert (
            training_deps.get_training_orchestrator(request)
            is injector.get(TrainingOrchestrator)
        )
        assert sc_deps.get_prefect_client(request) is ctx.shared.prefect_client
        assert sc_deps.get_image_fetcher(request) is ctx.sc.image_fetcher
        assert sc_deps.get_upstream_reader(request) is ctx.sc.upstream_reader
    finally:
        await close_flow_app_context(ctx)
