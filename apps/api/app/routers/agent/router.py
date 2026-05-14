from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_org, get_current_user
from app.api.schemas import (
    ChatRequest,
    GlobalChatRequest,
    QueryDataRequest,
    SetPanelRequest,
    SurfaceStateDocument,
)
from app.db.models import UserORM
from app.domain.models import (
    DEFAULT_ORG_ID,
    Organization,
    User,
)
from app.routers._common import get_container
from app.services.dataset_capability_guard import assert_not_sparse

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
# Dataset query endpoint
# ---------------------------------------------------------------------------


@router.post("/datasets/{dataset_id}/query")
async def query_dataset_data(
    dataset_id: str,
    body: QueryDataRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    c = get_container()
    dataset = await c.repository().get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if body.query_type == "wafer-points":
        assert_not_sparse(dataset)

    from app.agent.tools import execute_query_data

    return await execute_query_data(
        query_type=body.query_type,
        params=body.params,
        dataset_id=dataset_id,
        repository=c.repository(),
    )


# ---------------------------------------------------------------------------
# Dataset-scoped agent chat
# ---------------------------------------------------------------------------


@router.post("/datasets/{dataset_id}/agent/chat")
async def agent_chat(
    dataset_id: str,
    body: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
):
    c = get_container()
    cfg = c.config()

    dataset = await c.repository().get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if not cfg.llm.api_key:
        raise HTTPException(
            status_code=503,
            detail="LLM not configured. Set llm.api_key and llm.model in config.",
        )

    session_id = f"user-{current_user.id}-{dataset_id}"
    surface_id = "classify-sidebar"

    repo = c.repository()
    annotation_stats = await repo.get_annotation_stats(dataset_id)
    random_samples = await repo.get_random_samples(
        dataset_id,
        limit=int(cfg.agent.metadata_sample_size) if hasattr(cfg, "agent") else 100,
    )
    metadata_dicts = [
        s.get("metadata", {}) for s in random_samples if s.get("metadata")
    ]

    task_spec = dataset.task_spec or {}
    declared_metadata = (
        task_spec.get("metadata_schema") if isinstance(task_spec, dict) else None
    )
    label_space = (
        task_spec.get("label_space", []) if isinstance(task_spec, dict) else []
    )

    pred_summary = await repo.prediction_summary(dataset_id)
    has_predictions = pred_summary.get("total_predictions", 0) > 0
    has_embeddings = False

    from app.agent.assembler import assemble_prompt
    from app.agent.runtime import (
        ClassifyAgent,
        AgentAction,
        AgentDone,
        AgentMessage,
        AgentSidebarUpdate,
    )

    system_prompt = assemble_prompt(
        dataset_name=dataset.name,
        dataset_type=dataset.dataset_type or "unknown",
        sample_count=annotation_stats.get("total_samples", 0),
        label_space=label_space,
        annotation_stats=annotation_stats,
        metadata_dicts=metadata_dicts,
        declared_metadata=declared_metadata,
        has_predictions=has_predictions,
        has_embeddings=has_embeddings,
    )

    agent = ClassifyAgent(
        system_prompt=system_prompt,
        llm_base_url=cfg.llm.base_url,
        llm_api_key=cfg.llm.api_key,
        llm_model=cfg.llm.model,
        dataset_id=dataset_id,
        session_id=session_id,
        surface_id=surface_id,
        surface_store=c.surface_store(),
        repository=repo,
    )

    async def event_stream():
        async for event in agent.handle_message(body.message):
            if isinstance(event, AgentMessage):
                yield f"event: agent-message\ndata: {json.dumps({'content': event.content})}\n\n"
            elif isinstance(event, AgentAction):
                yield f"event: agent-action\ndata: {json.dumps({'tool': event.tool, 'summary': event.summary})}\n\n"
            elif isinstance(event, AgentSidebarUpdate):
                yield f"event: sidebar-update\ndata: {json.dumps({'surface_id': event.surface_id, 'panels': event.panels})}\n\n"
            elif isinstance(event, AgentDone):
                yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
    from app.services.scheduler import SchedulerService as _SchedulerService

    prefect_api_url = (
        cfg.prefect.api_url if hasattr(cfg, "prefect") else "http://localhost:4200/api"
    )
    scheduler_svc = _SchedulerService(prefect_api_url=prefect_api_url, repository=repo)

    from app.agent.global_runtime import GlobalAgent
    from app.agent.runtime import (
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
