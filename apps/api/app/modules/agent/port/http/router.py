from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from omegaconf import DictConfig
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.shared.sse.emit import emit_sse
from app.shared.sse.events import (
    AgentActionEvent,
    AgentMessageEvent,
    DoneEvent,
    SidebarUpdateEvent,
    SSEEvent,
)

from app.modules.agent.port.http.schemas import (
    GlobalChatRequest,
    SetPanelRequest,
    SurfaceStateDocument,
)
from app.modules.auth.port.http.deps import (
    get_current_org,
    get_current_user,
)
from app.shared.db.registry import UserORM
from app.modules.agent.app.services.global_runtime import GlobalAgent
from app.shared.api.schemas import (
    Organization,
    User,
)
from app.modules.models.app.services.model_service import ModelService
from app.modules.prediction.app.services.prediction_orchestrator import (
    PredictionOrchestrator,
)
from app.modules.schedules.app.services.scheduler import SchedulerService
from app.modules.training.app.services.orchestrator import TrainingOrchestrator
from app.shared.db.sql_repository import SqlRepository
from app.modules.agent.port.http.deps import (
    get_config,
    get_dataset_storage_factory,
    get_label_studio_client,
    get_model_service,
    get_orchestrator,
    get_prediction_orchestrator,
    get_repository,
    get_scheduler_service,
    get_session_factory,
    get_session_store,
    get_surface_store,
)
from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.shared.infrastructure.agent_runtime import (
    AgentAction,
    AgentDone,
    AgentMessage,
    AgentSidebarUpdate,
)
from app.shared.domain.protocols import LabelStudioClient
from app.shared.infrastructure.surface_store import SurfaceStore
from app.modules.agent.app.services.session_store import SessionStore

router = APIRouter(prefix="/api/v1", tags=["agent"])
_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agent / Display Surface endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{session_id}/surfaces/{surface_id}",
    response_model=SurfaceStateDocument,
)
async def get_surface_state(
    session_id: str,
    surface_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    surface_store: SurfaceStore = Depends(get_surface_store),
) -> SurfaceStateDocument:
    return await surface_store.get_state(session_id, surface_id)


@router.post(
    "/sessions/{session_id}/surfaces/{surface_id}/panels",
    response_model=SurfaceStateDocument,
)
async def set_surface_panel(
    session_id: str,
    surface_id: str,
    body: SetPanelRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    surface_store: SurfaceStore = Depends(get_surface_store),
) -> SurfaceStateDocument:
    return await surface_store.set_panel(session_id, surface_id, body.panel)


@router.delete(
    "/sessions/{session_id}/surfaces/{surface_id}/panels/{panel_id}",
    response_model=SurfaceStateDocument,
)
async def remove_surface_panel(
    session_id: str,
    surface_id: str,
    panel_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    surface_store: SurfaceStore = Depends(get_surface_store),
) -> SurfaceStateDocument:
    doc = await surface_store.remove_panel(session_id, surface_id, panel_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Panel not found")
    return doc


@router.post(
    "/sessions/{session_id}/surfaces/{surface_id}/import",
    response_model=SurfaceStateDocument,
)
async def import_surface_state(
    session_id: str,
    surface_id: str,
    body: SurfaceStateDocument,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    surface_store: SurfaceStore = Depends(get_surface_store),
) -> SurfaceStateDocument:
    return await surface_store.import_state(session_id, surface_id, body)


@router.get(
    "/sessions/{session_id}/surfaces/{surface_id}/export",
    response_model=SurfaceStateDocument,
)
async def export_surface_state(
    session_id: str,
    surface_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    surface_store: SurfaceStore = Depends(get_surface_store),
) -> SurfaceStateDocument:
    return await surface_store.export_state(session_id, surface_id)


# ---------------------------------------------------------------------------
# Global Agent Chat (platform-wide)
# ---------------------------------------------------------------------------


@router.post("/agent/chat")
async def global_agent_chat(
    body: GlobalChatRequest,
    current_user: UserORM = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    cfg: DictConfig = Depends(get_config),
    repo: SqlRepository = Depends(get_repository),
    session_factory: async_sessionmaker = Depends(get_session_factory),
    session_store: SessionStore = Depends(get_session_store),
    surface_store: SurfaceStore = Depends(get_surface_store),
    orchestrator: TrainingOrchestrator = Depends(get_orchestrator),
    prediction_orchestrator: PredictionOrchestrator = Depends(
        get_prediction_orchestrator
    ),
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
    model_service: ModelService = Depends(get_model_service),
    label_studio_client: LabelStudioClient = Depends(get_label_studio_client),
    dataset_storage_factory: DatasetStorageFactory = Depends(
        get_dataset_storage_factory
    ),
):
    if not cfg.llm.api_key:
        raise HTTPException(
            status_code=503,
            detail="LLM not configured. Set llm.api_key and llm.model in config.",
        )

    session_id = body.session_id or f"global-{current_user.id}"

    agent = GlobalAgent(
        llm_base_url=cfg.llm.base_url,
        llm_api_key=cfg.llm.api_key,
        llm_model=cfg.llm.model,
        session_store=session_store,
        surface_store=surface_store,
        repository=repo,
        dataset_storage_factory=dataset_storage_factory,
        session_factory=session_factory,
        orchestrator=orchestrator,
        prediction_orchestrator=prediction_orchestrator,
        scheduler_service=scheduler_service,
        model_service=model_service,
        label_studio_client=label_studio_client,
    )

    async def event_stream():
        async for event in agent.handle_message(
            session_id=session_id,
            user_id=str(current_user.id),
            user_email=current_user.email,
            org_id=org.id,
            org_name=org.name,
            context=body.context,
            user_message=body.message,
        ):
            if isinstance(event, AgentMessage):
                yield emit_sse(
                    SSEEvent(
                        AgentMessageEvent(
                            event_type="agent-message", content=event.content
                        )
                    )
                )
            elif isinstance(event, AgentAction):
                yield emit_sse(
                    SSEEvent(
                        AgentActionEvent(
                            event_type="agent-action",
                            tool=event.tool,
                            summary=event.summary,
                        )
                    )
                )
            elif isinstance(event, AgentSidebarUpdate):
                yield emit_sse(
                    SSEEvent(
                        SidebarUpdateEvent(
                            event_type="sidebar-update",
                            data={
                                "surface_id": event.surface_id,
                                "panels": event.panels,
                            },
                        )
                    )
                )
            elif isinstance(event, AgentDone):
                yield emit_sse(SSEEvent(DoneEvent(event_type="done")))

    return StreamingResponse(event_stream(), media_type="text/event-stream")
