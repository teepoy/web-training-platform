from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.shared.application.notification import WebhookNotificationSink
from app.shared.db.session import create_engine, create_session_factory
from app.shared.infrastructure.label_studio.client import LabelStudioClient
from app.shared.infrastructure.llm.client import OpenAICompatibleLlmClient
from app.shared.infrastructure.prefect.client import PrefectClient
from app.shared.infrastructure.storage.memory import InMemoryArtifactStorage
from app.shared.infrastructure.storage.minio import MinioArtifactStorage
from app.shared.infrastructure.surface_store import SurfaceStore


@dataclass
class SharedInfra:
    """Infrastructure shared by all modules.  Fields match composition.py:AppContainer."""

    config: Any  # AppConfig type alias
    db_engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    artifact_storage: Any  # ArtifactStorage type alias
    label_studio_client: Any  # LabelStudioClient
    llm_client: Any  # OpenAICompatibleLlmClient
    prefect_client: Any  # PrefectClient
    notification_sink: Any  # WebhookNotificationSink
    surface_store: Any  # SurfaceStore


@dataclass
class AppContext:
    """Full application context — shared infra + per-module contexts.

    Module context fields are all optional.  The composition root fills them
    during application bootstrap.
    """

    shared: SharedInfra

    # Module contexts — all optional, filled by composition root
    datasets: Any | None = None
    prediction: Any | None = None
    training: Any | None = None
    models: Any | None = None
    dashboard: Any | None = None
    preview: Any | None = None
    task_tracker: Any | None = None
    schedules: Any | None = None
    sensors: Any | None = None
    settings: Any | None = None
    agent: Any | None = None
    classify: Any | None = None
    auth: Any | None = None
    sc: Any | None = None


def build_shared_infra(cfg: Any) -> SharedInfra:
    """Build SharedInfra from config — pure shared infrastructure, no module wiring.

    Extracts the shared-infra creation logic from composition.py:_build_base_container()
    without importing any module-specific code.
    """

    db_engine = create_engine(
        db_url=str(cfg.db.url),
        echo=bool(cfg.db.echo),
    )
    session_factory = create_session_factory(db_engine)

    # Inline _build_artifact_storage logic (composition.py:117-129)
    kind = str(cfg.storage.kind)
    if kind == "memory":
        artifact_storage: Any = InMemoryArtifactStorage()
    elif kind == "minio":
        artifact_storage = MinioArtifactStorage(
            endpoint=str(cfg.storage.minio.endpoint),
            access_key=str(cfg.storage.minio.access_key),
            secret_key=str(cfg.storage.minio.secret_key),
            bucket=str(cfg.storage.minio.bucket),
            secure=bool(cfg.storage.minio.secure),
        )
    else:
        raise RuntimeError(f"Unsupported storage.kind: {kind}")

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
        llm_client=OpenAICompatibleLlmClient(
            base_url=str(cfg.llm.base_url),
            api_key=str(cfg.llm.api_key),
            model=str(cfg.llm.model),
            timeout_seconds=float(cfg.llm.timeout_seconds),
        ),
        prefect_client=prefect_client,
        notification_sink=notification_sink,
        surface_store=SurfaceStore(),
    )


def build_app_context(cfg: Any) -> AppContext:
    """Build full AppContext from config.

    Module contexts are initially None.  They will be filled by per-module
    init_xxx() functions called from the composition root in Task 18.
    """
    shared = build_shared_infra(cfg)
    return AppContext(shared=shared)
