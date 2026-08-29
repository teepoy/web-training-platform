from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from injector import Injector
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import AppConfig
from app.shared.application.notification import WebhookNotificationSink
from app.shared.db.session import (
    AppDatabaseSessionFactory,
    create_engine,
    create_session_factory,
)
from app.shared.domain.protocols import (
    ArtifactStorage,
    LabelStudioClient as LabelStudioClientPort,
    PrefectClient as PrefectClientPort,
)
from app.shared.infrastructure.label_studio.client import LabelStudioClient
from app.shared.infrastructure.prefect.client import PrefectClient
from app.shared.infrastructure.redis.event_publisher import RedisEventPublisher
from app.shared.infrastructure.storage.factory import build_artifact_storage
from app.shared.infrastructure.surface_store import SurfaceStore

if TYPE_CHECKING:
    from app.modules.agent.container import AgentContext
    from app.modules.auth.container import AuthContext
    from app.modules.dashboard.container import DashboardContext
    from app.modules.dataset_collections.container import DatasetCollectionsContext
    from app.modules.datasets.container import DatasetsContext
    from app.modules.models.container import ModelsContext
    from app.modules.prediction.container import PredictionContext
    from app.modules.sc.container import ScContext
    from app.modules.jobs.container import JobsContext
    from app.modules.storage.container import StorageContext
    from app.modules.training.container import TrainingContext


@dataclass
class SharedInfra:
    """Infrastructure shared by all modules."""

    config: AppConfig
    db_engine: AsyncEngine
    session_factory: AppDatabaseSessionFactory
    artifact_storage: ArtifactStorage
    label_studio_client: LabelStudioClientPort
    prefect_client: PrefectClientPort
    notification_sink: WebhookNotificationSink
    surface_store: SurfaceStore
    redis_event_publisher: RedisEventPublisher | None = None


@dataclass
class AppContext:
    """Full application context — shared infra + per-module contexts.

    Module context fields are all optional.  The composition root fills them
    during application bootstrap.

    Current state: this still carries module contexts as a transition layer
    from the old flat container.  Runtime consumers should prefer resolving
    typed Protocol/port bindings from ``injector`` instead of reaching across
    module contexts.

    Next step: shrink this object toward lifecycle ownership only, and let
    injector provider methods / constructor annotations own module service
    construction.
    """

    shared: SharedInfra

    # Module contexts — all optional, filled by composition root
    datasets: DatasetsContext | None = None
    dataset_collections: DatasetCollectionsContext | None = None
    prediction: PredictionContext | None = None
    training: TrainingContext | None = None
    storage: StorageContext | None = None
    models: ModelsContext | None = None
    dashboard: DashboardContext | None = None
    jobs: JobsContext | None = None
    agent: AgentContext | None = None
    auth: AuthContext | None = None
    sc: ScContext | None = None
    injector: Injector | None = None


def build_shared_infra(cfg: AppConfig) -> SharedInfra:
    """Build SharedInfra from config — pure shared infrastructure, no module wiring.

    Extracts the shared-infra creation logic from composition.py:_build_base_container()
    without importing any module-specific code.
    """

    db_engine = create_engine(
        db_url=str(cfg.db.url),
        echo=bool(cfg.db.echo),
    )
    session_factory = AppDatabaseSessionFactory(create_session_factory(db_engine))

    artifact_storage: ArtifactStorage = build_artifact_storage(cfg)

    prefect_client = PrefectClient(prefect_api_url=str(cfg.prefect.api_url))
    notification_sink = WebhookNotificationSink(
        endpoint=str(cfg.notification.webhook.endpoint),
        timeout_seconds=int(cfg.notification.webhook.timeout_seconds),
    )

    return SharedInfra(
        config=cfg,
        db_engine=db_engine,
        session_factory=session_factory,
        artifact_storage=artifact_storage,
        label_studio_client=LabelStudioClient(
            url=str(cfg.label_studio.url),
            api_key=str(cfg.label_studio.api_key),
        ),
        prefect_client=prefect_client,
        notification_sink=notification_sink,
        surface_store=SurfaceStore(),
    )


def build_app_context(cfg: AppConfig) -> AppContext:
    """Build full AppContext from config.

    Module contexts are initially None.  They will be filled by per-module
    init_xxx() functions called from the composition root in Task 18.
    """
    shared = build_shared_infra(cfg)
    return AppContext(shared=shared)
