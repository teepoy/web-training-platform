from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from omegaconf import DictConfig  # pyright: ignore[reportMissingImports]

from app.domain.models import Organization, User
from app.modules.auth.interfaces.controllers.deps import (
    get_current_org,
    get_current_user,
)
from app.modules.classify.interfaces.dtos.schemas import ChatRequest, QueryDataRequest
from app.shared.db.sql_repository import SqlRepository
from app.shared.deps import (
    get_config,
    get_repository,
    get_sample_access_factory,
    get_surface_store,
)
from app.modules.datasets.application.sample_access.factory import SampleAccessFactory
from app.shared.infrastructure.surface_store import SurfaceStore

router = APIRouter(prefix="/api/v1", tags=["classify"])


@router.post("/datasets/{dataset_id}/query")
async def query_dataset_data(
    dataset_id: str,
    body: QueryDataRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    sample_factory: SampleAccessFactory = Depends(get_sample_access_factory),
) -> dict:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if body.query_type == "wafer-points":
        access = sample_factory.create(dataset.storage_mode)
        if not access.capabilities().get("can_list_samples"):
            raise HTTPException(
                status_code=409,
                detail="Wafer points query is not supported for this dataset's storage mode",
            )

    from app.modules.classify.infrastructure.tools.tools import execute_query_data

    return await execute_query_data(
        query_type=body.query_type,
        params=body.params,
        dataset_id=dataset_id,
        repository=repo,
    )


@router.post("/datasets/{dataset_id}/agent/chat")
async def agent_chat(
    dataset_id: str,
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    cfg: DictConfig = Depends(get_config),
    repo: SqlRepository = Depends(get_repository),
    surface_store: SurfaceStore = Depends(get_surface_store),
):
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if not cfg.llm.api_key:
        raise HTTPException(
            status_code=503,
            detail="LLM not configured. Set llm.api_key and llm.model in config.",
        )

    session_id = f"user-{current_user.id}-{dataset_id}"
    surface_id = "classify-sidebar"

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

    from app.modules.classify.application.services.runtime import (
        AgentAction,
        AgentDone,
        AgentMessage,
        AgentSidebarUpdate,
        ClassifyAgent,
    )
    from app.modules.classify.infrastructure.tools.assembler import assemble_prompt

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
        surface_store=surface_store,
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
