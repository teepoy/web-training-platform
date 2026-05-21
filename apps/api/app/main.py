from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.routing import compile_path

from app.composition import build_app_container
from app.modules.auth.interfaces.controllers.deps import (
    get_current_org,
    get_current_user,
)
from app.shared.api.schemas import (
    DashboardResponse,
    JobQueueStats,
    RecentJobSummary,
    ServiceStatus,
    WorkPoolStatus,
)
from app.core.config import _resolve_gpu_worker_url, load_config
from app.shared.infrastructure.label_studio.session import (
    create_ls_engine,
    create_ls_session_factory,
)
from app.shared.db.registry import OrganizationORM
from app.shared.db.session import create_engine, create_session_factory, init_db
from app.shared.api.schemas import DEFAULT_ORG_ID, Organization, User
from app.modules.registry import EXTENSION_ROUTERS, MODULE_ROUTERS
from app.modules.presets.registry import PresetRegistry
from app.shared.infrastructure.label_studio.read_repository import LsReadRepository
from app.modules.sensors.infrastructure.repositories.repository import (
    SensorRepositoryImpl,
)
from app.shared.db.sql_repository import SqlRepository
from app.modules.sensors.domain.entities.registry import SensorRegistry
from app.shared.application.artifacts import ArtifactService
from app.modules.auth.application.services.auth_service import AuthService
from app.shared.infrastructure.workers.embedding import EmbeddingClient
from app.modules.training.infrastructure.engines.local_kubeflow import (
    KubeflowTrainingOperatorEngine,
    LocalProcessEngine,
)
from app.modules.datasets.application.services.feature_ops import FeatureOpsService
from app.shared.infrastructure.workers.gpu_worker import GpuWorkerClient
from app.shared.infrastructure.workers.inference_worker import InferenceWorkerClient
from app.modules.training.infrastructure.clients.kubeflow_client import KubeflowClient
from app.modules.models.application.services.model_service import ModelService
from app.shared.application.notification import WebhookNotificationSink
from app.modules.training.application.services.orchestrator import TrainingOrchestrator
from app.modules.prediction.application.services.prediction_orchestrator import (
    PredictionOrchestrator,
)
from app.modules.prediction.application.services.prediction_service import (
    PredictionService,
)
from app.modules.training.infrastructure.engines.prefect_engine import (
    PrefectWorkPoolEngine,
)
from app.modules.preview.application.services.preview_service import PreviewService
from app.modules.preview.application.services.preview_store import PreviewStore
from app.modules.preview.application.services.preview_upstream import (
    MockUpstreamAdapter,
    PreviewUpstreamRouter,
    UpstreamAdapter,
)
from app.modules.datasets.application.sample_access.factory import SampleAccessFactory
from app.modules.sensors.application.services.sensor_dispatch import (
    SensorDispatchService,
)
from app.modules.dashboard.application.services.service_health import (
    ServiceHealthService,
)
from app.modules.agent.application.services.session_store import SessionStore
from app.shared.infrastructure.surface_store import SurfaceStore
from app.modules.task_tracker.application.services.task_tracker import (
    TaskTrackerService,
)
from app.shared.infrastructure.label_studio import get_label_studio, init_label_studio
from app.shared.infrastructure.llm import get_llm, init_llm
from app.shared.infrastructure.prefect import get_prefect, init_prefect
from app.shared.infrastructure.storage import get_storage, init_storage

_logger = logging.getLogger(__name__)


def _build_state_container(api: FastAPI, cfg: Any) -> None:
    try:
        api.state.container = build_app_container(cfg)
    except RuntimeError:
        if not container.config._has_override:
            raise
        api.state.container = build_app_container(load_config())
    if container.prefect_client._has_override:
        api.state.container.prefect_client = container.prefect_client()


class SingletonProvider:
    def __init__(self, factory: Callable[[], object]) -> None:
        self._factory = factory
        self._override: object | None = None
        self._has_override = False
        self._instance: object | None = None

    def __call__(self) -> Any:
        if self._has_override:
            return self._override
        if self._instance is None:
            self._instance = self._factory()
        return self._instance

    def override(self, provider: object) -> None:
        self._override = provider() if callable(provider) else provider
        self._has_override = True

    def reset_override(self) -> None:
        self._override = None
        self._has_override = False

    def reset(self) -> None:
        self._instance = None


class AppServices:
    def __init__(self) -> None:
        self.config = SingletonProvider(load_config)
        self.db_engine = SingletonProvider(
            lambda: create_engine(
                db_url=str(self.config().db.url),
                echo=bool(self.config().db.echo),
            )
        )
        self.session_factory = SingletonProvider(
            lambda: create_session_factory(self.db_engine())
        )
        self.repository = SingletonProvider(
            lambda: SqlRepository(session_factory=self.session_factory())
        )
        self.artifact_storage = SingletonProvider(get_storage)
        self.label_studio_client = SingletonProvider(get_label_studio)
        self.prefect_client = SingletonProvider(get_prefect)
        self.llm_client = SingletonProvider(get_llm)
        self.ls_engine = SingletonProvider(
            lambda: create_ls_engine(
                database_url=str(self.config().label_studio.database_url)
            )
        )
        self.ls_session_factory = SingletonProvider(
            lambda: create_ls_session_factory(engine=self.ls_engine())
        )
        self.ls_read_repository = SingletonProvider(
            lambda: LsReadRepository(session_factory=self.ls_session_factory())
        )
        self.embedding_service = SingletonProvider(
            lambda: EmbeddingClient(
                grpc_target=str(self.config().embedding.grpc_target)
            )
        )
        self.inference_worker = SingletonProvider(
            lambda: InferenceWorkerClient(
                base_url=str(self.config().inference.base_url)
            )
        )
        self.gpu_worker = SingletonProvider(
            lambda: GpuWorkerClient(base_url=_resolve_gpu_worker_url(self.config()))
        )
        self.kubeflow_client = SingletonProvider(
            lambda: KubeflowClient(
                namespace=str(self.config().k8s.namespace),
                group=str(self.config().kubeflow.group),
                version=str(self.config().kubeflow.version),
                plural=str(self.config().kubeflow.plural),
                in_cluster=bool(self.config().k8s.incluster),
                kubeconfig=str(self.config().k8s.kubeconfig),
            )
        )
        self.preset_registry = SingletonProvider(
            lambda: PresetRegistry(
                presets_dir=str(self.config().presets.dir),
                strict=bool(self.config().presets.strict),
            )
        )
        self.sensor_registry = SingletonProvider(
            lambda: SensorRegistry(
                sensors_dir=str(self.config().sensors.dir),
                strict=bool(self.config().sensors.strict),
            )
        )
        self.sensor_repository = SingletonProvider(
            lambda: SensorRepositoryImpl(session_factory=self.session_factory())
        )
        self.sensor_dispatch = SingletonProvider(
            lambda: SensorDispatchService(
                repository=self.sensor_repository(),
                prefect_client=self.prefect_client(),
            )
        )
        self.sample_access_factory = SingletonProvider(
            lambda: SampleAccessFactory(repo=self.repository())
        )
        self.service_health = SingletonProvider(
            lambda: ServiceHealthService(
                config=self.config(),
                prefect_client=self.prefect_client(),
                embedding_client=self.embedding_service(),
            )
        )
        self.task_tracker = SingletonProvider(
            lambda: TaskTrackerService(
                repository=self.repository(),
                prefect_client=self.prefect_client(),
                config=self.config(),
            )
        )
        self.auth_service = SingletonProvider(AuthService)
        self.local_engine = SingletonProvider(
            lambda: LocalProcessEngine(storage=self.artifact_storage())
        )
        self.kubeflow_engine = SingletonProvider(
            lambda: KubeflowTrainingOperatorEngine(
                kubeflow_client=self.kubeflow_client(),
                image=str(self.config().kubeflow.image),
                storage=self.artifact_storage(),
            )
        )
        self.prefect_engine = SingletonProvider(
            lambda: PrefectWorkPoolEngine(
                prefect_client=self.prefect_client(),
                work_pool_name=str(self.config().prefect.work_pool_name),
                work_pool_type=str(self.config().prefect.work_pool_type),
                flow_name=str(self.config().prefect.flow_name),
                concurrency_limit=int(self.config().prefect.concurrency_limit),
                preset_registry=self.preset_registry(),
            )
        )
        self.execution_engine = SingletonProvider(self._create_execution_engine)
        self.notification_sink = SingletonProvider(
            lambda: WebhookNotificationSink(
                endpoint=str(self.config().notification.webhook.endpoint),
                timeout_seconds=int(self.config().notification.webhook.timeout_seconds),
            )
        )
        self.artifacts = SingletonProvider(
            lambda: ArtifactService(
                storage=self.artifact_storage(),
                repository=self.repository(),
            )
        )
        self.orchestrator = SingletonProvider(
            lambda: TrainingOrchestrator(
                engine=self.execution_engine(),
                notification_sink=self.notification_sink(),
                repository=self.repository(),
                artifact_service=self.artifacts(),
            )
        )
        self.feature_ops = SingletonProvider(
            lambda: FeatureOpsService(
                repository=self.repository(),
                embedding_service=self.embedding_service(),
                inference_worker=self.inference_worker(),
                gpu_worker=self.gpu_worker(),
            )
        )
        self.model_service = SingletonProvider(
            lambda: ModelService(
                repository=self.repository(),
                artifact_storage=self.artifact_storage(),
            )
        )
        self.prediction_service = SingletonProvider(
            lambda: PredictionService(
                repository=self.repository(),
                artifact_storage=self.artifact_storage(),
                config=self.config(),
                embedding_client=self.embedding_service(),
                llm_client=self.llm_client(),
                inference_worker=self.inference_worker(),
                gpu_worker=self.gpu_worker(),
            )
        )
        self.prediction_orchestrator = SingletonProvider(
            lambda: PredictionOrchestrator(
                prefect_client=self.prefect_client(),
                repository=self.repository(),
            )
        )
        self.surface_store = SingletonProvider(SurfaceStore)
        self.session_store = SingletonProvider(SessionStore)
        self.mock_upstream = SingletonProvider(MockUpstreamAdapter)
        self.preview_upstream = SingletonProvider(
            lambda: PreviewUpstreamRouter(
                upstreams=self._make_upstreams(self.mock_upstream(), None)
            )
        )
        self.preview_store = SingletonProvider(PreviewStore)
        self.preview_service = SingletonProvider(
            lambda: PreviewService(
                store=self.preview_store(), upstream=self.preview_upstream()
            )
        )

    def _create_execution_engine(self) -> object:
        engine = str(self.config().execution.engine)
        if engine == "local":
            return self.local_engine()
        if engine == "kubeflow":
            return self.kubeflow_engine()
        if engine == "prefect":
            return self.prefect_engine()
        raise RuntimeError(f"Unsupported execution.engine: {engine}")

    @staticmethod
    def _make_upstreams(
        mock: UpstreamAdapter, s3: UpstreamAdapter | None
    ) -> dict[str, UpstreamAdapter]:
        upstreams = {"mock": mock}
        if s3 is not None:
            upstreams["s3"] = s3
        return upstreams

    def reset_singletons(self) -> None:
        for value in vars(self).values():
            if isinstance(value, SingletonProvider):
                value.reset()


container = AppServices()
services = container


async def _sync_file_presets_to_db() -> None:
    registry = container.preset_registry()
    repo = container.repository()
    existing_default_org = await repo.get_organization(DEFAULT_ORG_ID)
    if existing_default_org is None:
        await repo.create_organization(
            OrganizationORM(
                id=DEFAULT_ORG_ID,
                name="Default",
                slug="default",
            )
        )
    existing = await repo.list_preset_ids()
    for spec in registry.list_presets():
        if spec.id in existing:
            continue
        legacy = registry.preset_to_api_dict(spec)
        await repo.ensure_preset_row(
            preset_id=spec.id,
            name=spec.name,
            model_spec=legacy.get("model_spec", {})
            if isinstance(legacy.get("model_spec", {}), dict)
            else {},
            omegaconf_yaml=str(legacy.get("omegaconf_yaml", "")),
            dataloader_ref=str(legacy.get("dataloader_ref", "")),
        )


def _strip_api_prefix(router: Any) -> None:
    for route in router.routes:
        path = getattr(route, "path", "")
        if path == "/api/v1":
            new_path = ""
        elif path.startswith("/api/v1/"):
            new_path = path.removeprefix("/api/v1")
        else:
            continue
        route.path = new_path
        route.path_regex, route.path_format, route.param_convertors = compile_path(
            new_path
        )


def _register_legacy_provider_overrides(api: FastAPI) -> None:
    return None


@asynccontextmanager
async def lifespan(api: FastAPI):
    cfg = container.config()
    if not container.artifact_storage._has_override:
        try:
            init_storage(cfg)
        except RuntimeError:
            if not container.config._has_override:
                raise
            init_storage(load_config())
    if not container.label_studio_client._has_override:
        init_label_studio(cfg)
    if not container.llm_client._has_override:
        init_llm(cfg)
    if not container.prefect_client._has_override:
        init_prefect(cfg)
    _build_state_container(api, cfg)
    if bool(cfg.db.auto_create):
        await init_db(container.db_engine())

    registry = container.preset_registry()
    count = registry.load()
    _logger.info("Preset registry: %d presets loaded", count)
    try:
        sensor_count = container.sensor_registry().load()
    except Exception:
        sensor_count = 0
    _logger.info("Sensor registry: %d sensors loaded", sensor_count)
    await _sync_file_presets_to_db()

    yield

    prefect_client = container.prefect_client()
    close = getattr(prefect_client, "close", None)
    if close is not None:
        await close()
    embedding_client = container.embedding_service()
    embedding_close = getattr(embedding_client, "close", None)
    if embedding_close is not None:
        embedding_close()


app = FastAPI(title="Online Finetune API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in [*MODULE_ROUTERS, *EXTENSION_ROUTERS]:
    _strip_api_prefix(r)
    app.include_router(r, prefix="/api/v1")
_register_legacy_provider_overrides(app)


# ---------------------------------------------------------------------------
# Core endpoints not belonging to a single domain
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str | bool]:
    cfg = container.config()
    return {
        "status": "ok",
        "auth_enabled": bool(getattr(cfg.auth, "enabled", True)),
    }


@app.get("/api/v1/health")
def api_health() -> dict[str, str | bool]:
    return health()


@app.get("/api/v1/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> DashboardResponse:
    repo = container.repository()
    cfg = container.config()
    service_health = container.service_health()

    all_jobs = await repo.list_jobs(org_id=org.id)
    stats = JobQueueStats()
    for j in all_jobs:
        s = j.status.value if hasattr(j.status, "value") else str(j.status)
        if s == "queued":
            stats.queued += 1
        elif s == "running":
            stats.running += 1
        elif s == "completed":
            stats.completed += 1
        elif s == "failed":
            stats.failed += 1
        elif s == "cancelled":
            stats.cancelled += 1

    sorted_jobs = sorted(all_jobs, key=lambda j: j.created_at, reverse=True)[:20]
    recent: list[RecentJobSummary] = [
        RecentJobSummary(
            id=j.id,
            dataset_id=j.dataset_id,
            preset_id=j.preset_id,
            status=j.status.value if hasattr(j.status, "value") else str(j.status),
            created_by=j.created_by,
            created_at=j.created_at
            if isinstance(j.created_at, str)
            else j.created_at.isoformat(),
            updated_at=j.updated_at
            if isinstance(j.updated_at, str)
            else j.updated_at.isoformat(),
        )
        for j in sorted_jobs
    ]

    work_pool: WorkPoolStatus | None = None
    prefect_connected = False
    engine_name = str(cfg.execution.engine)

    if engine_name == "prefect":
        pool_name = str(cfg.prefect.work_pool_name)
        try:
            prefect_client = container.prefect_client()
            pool_data = await prefect_client.get_work_pool(pool_name)
            prefect_connected = True

            slots_used = 0
            try:
                running_runs = await prefect_client.filter_flow_runs(
                    work_pool_name=pool_name,
                    state_types=["RUNNING"],
                )
                slots_used = len(running_runs)
            except Exception:
                pass

            work_pool = WorkPoolStatus(
                name=pool_data.get("name", pool_name),
                type=pool_data.get("type", "unknown"),
                is_paused=pool_data.get("is_paused", False),
                concurrency_limit=pool_data.get("concurrency_limit"),
                slots_used=slots_used,
                status="paused" if pool_data.get("is_paused", False) else "ready",
            )
        except Exception:
            pass

    services = [
        ServiceStatus.model_validate(item.model_dump())
        for item in await service_health.check_all()
    ]

    return DashboardResponse(
        work_pool=work_pool,
        job_queue=stats,
        recent_jobs=recent,
        services=services,
        prefect_connected=prefect_connected,
    )
