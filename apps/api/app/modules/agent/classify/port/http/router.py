from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.shared.sse.emit import emit_sse
from app.shared.sse.events import (
    AgentActionEvent,
    AgentMessageEvent,
    DoneEvent,
    SidebarUpdateEvent,
    SSEEvent,
)

from app.shared.api.schemas import Organization, User
from app.modules.auth.port.http.deps import (
    get_current_org,
    get_current_user,
)
from app.modules.agent.classify.port.http.deps import (
    ConfigDep,
    DatasetStorageFactoryDep,
    RepositoryDep,
    SurfaceStoreDep,
)
from app.modules.agent.classify.port.http.schemas import ChatRequest, QueryDataRequest

router = APIRouter(prefix="/api/v1", tags=["classify"])


@router.post("/datasets/{dataset_id}/query")
async def query_dataset_data(
    dataset_id: str,
    body: QueryDataRequest,
    repo: RepositoryDep,
    factory: DatasetStorageFactoryDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    from app.modules.agent.classify.adapter.tools.tools import execute_query_data

    return await execute_query_data(
        query_type=body.query_type,
        params=body.params,
        dataset_id=dataset_id,
        factory=factory,
        org_id=org.id,
    )


@router.post("/datasets/{dataset_id}/agent/chat")
async def agent_chat(
    dataset_id: str,
    body: ChatRequest,
    cfg: ConfigDep,
    repo: RepositoryDep,
    factory: DatasetStorageFactoryDep,
    surface_store: SurfaceStoreDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
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

    storage = await factory.open(dataset_id, org.id)
    annotation_stats = await storage.get_annotation_stats()

    random_samples, _ = await storage.list_samples(
        limit=int(cfg.agent.metadata_sample_size) if hasattr(cfg, "agent") else 100,
        random_seed=hash(uuid4()),
    )
    metadata_dicts = [s.metadata for s in random_samples if s.metadata]

    task_spec = dataset.task_spec or {}
    declared_metadata = (
        task_spec.get("metadata_schema") if isinstance(task_spec, dict) else None
    )
    label_space = (
        task_spec.get("label_space", []) if isinstance(task_spec, dict) else []
    )

    pred_summary = await storage.prediction_summary()
    has_predictions = pred_summary.get("total_predictions", 0) > 0
    has_embeddings = False

    from app.modules.agent.classify.app.services.runtime import (
        AgentAction,
        AgentDone,
        AgentMessage,
        AgentSidebarUpdate,
        ClassifyAgent,
    )
    from app.modules.agent.classify.adapter.tools.assembler import assemble_prompt

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
        dataset_storage_factory=factory,
        org_id=org.id,
    )

    async def event_stream():
        async for event in agent.handle_message(body.message):
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
