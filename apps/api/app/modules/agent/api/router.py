from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.modules.agent.api.schemas import (
    GlobalChatRequest,
    SetPanelRequest,
    SurfaceStateDocument,
)
from app.modules.auth.api.deps import get_current_org, get_current_user
from app.shared.db.registry import UserORM
from app.domain.models import (
    DEFAULT_ORG_ID,
    Organization,
    User,
)
from app.shared.deps import get_container

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
) -> SurfaceStateDocument:
    c = get_container()
    return await c.surface_store().get_state(session_id, surface_id)


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
) -> SurfaceStateDocument:
    c = get_container()
    return await c.surface_store().set_panel(session_id, surface_id, body.panel)


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
) -> SurfaceStateDocument:
    c = get_container()
    doc = await c.surface_store().remove_panel(session_id, surface_id, panel_id)
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
) -> SurfaceStateDocument:
    c = get_container()
    return await c.surface_store().import_state(session_id, surface_id, body)


@router.get(
    "/sessions/{session_id}/surfaces/{surface_id}/export",
    response_model=SurfaceStateDocument,
)
async def export_surface_state(
    session_id: str,
    surface_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> SurfaceStateDocument:
    c = get_container()
    return await c.surface_store().export_state(session_id, surface_id)


# ---------------------------------------------------------------------------
# Global Agent Chat (platform-wide)
# ---------------------------------------------------------------------------


@router.post("/agent/chat")
async def global_agent_chat(
    body: GlobalChatRequest,
    current_user: UserORM = Depends(get_current_user),
):
    c = get_container()
    cfg = c.config()

    if not cfg.llm.api_key:
        raise HTTPException(
            status_code=503,
            detail="LLM not configured. Set llm.api_key and llm.model in config.",
        )

    session_id = body.session_id or f"global-{current_user.id}"

    org_id = DEFAULT_ORG_ID
    org_name = "Default"

    repo = c.repository()
    from app.modules.schedules.application.scheduler import (
        SchedulerService as _SchedulerService,
    )

    prefect_api_url = (
        cfg.prefect.api_url if hasattr(cfg, "prefect") else "http://localhost:4200/api"
    )
    scheduler_svc = _SchedulerService(prefect_api_url=prefect_api_url, repository=repo)

    from app.modules.agent.application.global_runtime import GlobalAgent
    from app.shared.infrastructure.agent_runtime import (
        AgentAction,
        AgentDone,
        AgentMessage,
        AgentSidebarUpdate,
    )

    agent = GlobalAgent(
        llm_base_url=cfg.llm.base_url,
        llm_api_key=cfg.llm.api_key,
        llm_model=cfg.llm.model,
        session_store=c.session_store(),
        surface_store=c.surface_store(),
        repository=repo,
        orchestrator=c.orchestrator(),
        prediction_orchestrator=c.prediction_orchestrator(),
        scheduler_service=scheduler_svc,
        model_service=c.model_service(),
        preset_registry=c.preset_registry(),
        label_studio_client=c.label_studio_client(),
    )

    async def event_stream():
        async for event in agent.handle_message(
            session_id=session_id,
            user_id=str(current_user.id),
            user_email=current_user.email,
            org_id=org_id,
            org_name=org_name,
            context=body.context,
            user_message=body.message,
        ):
            if isinstance(event, AgentMessage):
                yield f"event: agent-message\ndata: {json.dumps({'content': event.content})}\n\n"
            elif isinstance(event, AgentAction):
                yield f"event: agent-action\ndata: {json.dumps({'tool': event.tool, 'summary': event.summary})}\n\n"
            elif isinstance(event, AgentSidebarUpdate):
                yield f"event: sidebar-update\ndata: {json.dumps({'surface_id': event.surface_id, 'panels': event.panels})}\n\n"
            elif isinstance(event, AgentDone):
                yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
