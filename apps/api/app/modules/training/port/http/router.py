from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.shared.api.schemas import PaginatedResponse
from app.modules.auth.port.http.deps import (
    get_current_org,
    get_current_user,
    require_superadmin,
)
from app.shared.api.schemas import (
    Organization,
    TrainingEvent,
    TrainingJob,
    User,
    DatasetStorageMode,
)
from app.modules.models.port.http.schemas import (
    SetPublicRequest,
    SetPublicResponse,
)
from app.modules.training.port.http.deps import (
    RepositoryDep,
    TrainingOrchestratorDep,
)
from app.modules.training.port.http.schemas import (
    CreateTrainingJobRequest,
    MarkLeftResponse,
)
from app.modules.datasets.port.local import validate_trainer_for_dataset
from app.modules.types import catalog
from app.shared.api.schemas import CancelJobResponse
from app.shared.sse.emit import emit_sse
from app.shared.sse.events import SSEEvent, TrainingStatusEvent

router = APIRouter(prefix="/api/v1", tags=["training"])


@router.get("/trainers")
async def list_trainers_route(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[dict]:
    return [
        {
            "id": t["id"],
            "name": t["name"],
            "view_type": t["view_id"],
            "trainable": True,
        }
        for t in _list_trainer_metadata()
    ]


def _list_trainer_metadata() -> list[dict[str, str]]:
    return [
        catalog.get_trainer_meta(trainer_id)
        for trainer_id in catalog.list_trainer_ids()
    ]


@router.get("/trainers/{trainer_id}")
async def get_trainer_route(
    trainer_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    try:
        trainer_meta = catalog.get_trainer_meta(trainer_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Trainer not found") from None
    return {
        "id": trainer_meta["id"],
        "name": trainer_meta["name"],
        "view_type": trainer_meta["view_id"],
        "trainable": True,
    }


@router.post("/training-jobs", response_model=TrainingJob)
async def create_training_job(
    payload: CreateTrainingJobRequest,
    repo: RepositoryDep,
    orchestrator: TrainingOrchestratorDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TrainingJob:
    dataset = await repo.get_dataset(payload.dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    if dataset.storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE and not dataset.dataset_type in (
        "image_sc",
    ):
        raise HTTPException(
            status_code=409,
            detail="Training is not supported for this dataset's storage mode",
        )
    validate_trainer_for_dataset(
        trainer_id=payload.trainer_id,
        dataset_type=dataset.dataset_type,
        view_types=dataset.view_types,
        storage_mode=dataset.storage_mode.value,
    )
    job = TrainingJob(
        dataset_id=payload.dataset_id,
        trainer_id=payload.trainer_id,
        created_by=current_user.id,
        org_id=org.id,
    )
    try:
        return await orchestrator.start_job(job)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Failed to start training job: {exc}"
        )


@router.get("/training-jobs", response_model=list[TrainingJob])
async def list_jobs(
    repo: RepositoryDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    dataset_id: str | None = Query(default=None, description="Filter by dataset"),
) -> list[TrainingJob]:
    return await repo.list_jobs(org_id=org.id, dataset_id=dataset_id)


@router.get("/training-jobs/{job_id}", response_model=TrainingJob)
async def get_job(
    job_id: str,
    repo: RepositoryDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TrainingJob:
    job = await repo.get_job(job_id, org_id=org.id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/training-jobs/{job_id}/cancel", response_model=CancelJobResponse)
async def cancel_job(
    job_id: str,
    orchestrator: TrainingOrchestratorDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> CancelJobResponse:
    try:
        ok = await orchestrator.cancel_job(job_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to cancel job: {exc}")
    return CancelJobResponse(cancelled=ok)


@router.get("/training-jobs/{job_id}/events")
async def get_job_events(
    job_id: str,
    request: Request,
    repo: RepositoryDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
):
    if await repo.get_job(job_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="job not found")

    async def event_stream():
        idx = 0
        while True:
            if await request.is_disconnected():
                break
            events = await repo.list_events(job_id)
            while idx < len(events):
                ev = events[idx]
                yield emit_sse(
                    SSEEvent(
                        TrainingStatusEvent(
                            event_type="status",
                            job_id=ev.job_id,
                            ts=ev.ts,
                            level=ev.level,
                            message=ev.message,
                            payload=ev.payload,
                        )
                    )
                )
                idx += 1
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get(
    "/training-jobs/{job_id}/events/history",
    response_model=PaginatedResponse[TrainingEvent],
)
async def get_job_events_history(
    job_id: str,
    repo: RepositoryDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> PaginatedResponse[TrainingEvent]:
    if await repo.get_job(job_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    items, total = await repo.list_events_paginated(job_id, offset=offset, limit=limit)
    return PaginatedResponse(items=items, total=total)


@router.post("/training-jobs/{job_id}/mark-left", response_model=MarkLeftResponse)
async def mark_user_left(
    job_id: str,
    repo: RepositoryDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> MarkLeftResponse:
    if await repo.get_job(job_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    return MarkLeftResponse(marked=await repo.mark_user_left(job_id))


@router.patch("/training-jobs/{job_id}/public", response_model=SetPublicResponse)
async def set_job_public(
    job_id: str,
    payload: SetPublicRequest,
    repo: RepositoryDep,
    current_user: User = Depends(get_current_user),
) -> SetPublicResponse:
    await require_superadmin(current_user=current_user)
    ok = await repo.set_job_public(job_id, payload.is_public)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found")
    return SetPublicResponse(ok=True)
