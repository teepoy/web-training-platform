from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.shared.api.schemas import PaginatedResponse
from app.modules.auth.interfaces.controllers.deps import (
    get_current_org,
    get_current_user,
    require_superadmin,
)
from app.shared.api.schemas import Organization, TrainingEvent, TrainingJob, User
from app.modules.datasets.application.sample_access.factory import SampleAccessFactory
from app.modules.models.interfaces.dtos.schemas import (
    SetPublicRequest,
    SetPublicResponse,
)
from app.modules.training.interfaces.dtos.schemas import (
    CreateTrainingJobRequest,
    MarkLeftResponse,
)
from app.modules.presets.registry import PresetRegistry
from app.modules.training.application.services.orchestrator import TrainingOrchestrator
from app.shared.db.sql_repository import SqlRepository
from app.shared.deps import (
    get_orchestrator,
    get_preset_registry,
    get_repository,
    get_sample_access_factory,
)
from app.shared.application.compatibility import validate_dataset_preset_training
from app.shared.api.schemas import CancelJobResponse

router = APIRouter(prefix="/api/v1", tags=["training"])


@router.get("/training-presets")
async def list_presets(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    registry: PresetRegistry = Depends(get_preset_registry),
) -> list[dict]:
    return [registry.preset_to_api_dict(p) for p in registry.list_presets()]


@router.get("/training-presets/{preset_id}")
async def get_preset(
    preset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    registry: PresetRegistry = Depends(get_preset_registry),
) -> dict:
    spec = registry.get_preset(preset_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    return registry.preset_to_api_dict(spec)


@router.post("/training-jobs", response_model=TrainingJob)
async def create_training_job(
    payload: CreateTrainingJobRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    sample_factory: SampleAccessFactory = Depends(get_sample_access_factory),
    registry: PresetRegistry = Depends(get_preset_registry),
    orchestrator: TrainingOrchestrator = Depends(get_orchestrator),
) -> TrainingJob:
    dataset = await repo.get_dataset(payload.dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    access = sample_factory.create(dataset.storage_mode)
    if not access.capabilities().get("can_train"):
        raise HTTPException(
            status_code=409,
            detail="Training is not supported for this dataset's storage mode",
        )
    preset = registry.get_preset(payload.preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="preset not found")
    if not preset.trainable:
        raise HTTPException(
            status_code=422,
            detail=(
                f"preset '{preset.id}' is inference-only and does not support training jobs"
            ),
        )
    try:
        validate_dataset_preset_training(dataset, preset)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    job = TrainingJob(
        dataset_id=payload.dataset_id,
        preset_id=payload.preset_id,
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
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
) -> list[TrainingJob]:
    return await repo.list_jobs(org_id=org.id)


@router.get("/training-jobs/{job_id}", response_model=TrainingJob)
async def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
) -> TrainingJob:
    job = await repo.get_job(job_id, org_id=org.id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/training-jobs/{job_id}/cancel", response_model=CancelJobResponse)
async def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    orchestrator: TrainingOrchestrator = Depends(get_orchestrator),
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
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
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
                line = f"data: {json.dumps(events[idx].model_dump(mode='json'))}\n\n"
                yield line
                idx += 1
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get(
    "/training-jobs/{job_id}/events/history",
    response_model=PaginatedResponse[TrainingEvent],
)
async def get_job_events_history(
    job_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
) -> PaginatedResponse[TrainingEvent]:
    if await repo.get_job(job_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    items, total = await repo.list_events_paginated(job_id, offset=offset, limit=limit)
    return PaginatedResponse(items=items, total=total)


@router.post("/training-jobs/{job_id}/mark-left", response_model=MarkLeftResponse)
async def mark_user_left(
    job_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
) -> MarkLeftResponse:
    if await repo.get_job(job_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    return MarkLeftResponse(marked=await repo.mark_user_left(job_id))


@router.patch("/training-jobs/{job_id}/public", response_model=SetPublicResponse)
async def set_job_public(
    job_id: str,
    payload: SetPublicRequest,
    current_user: User = Depends(get_current_user),
    repo: SqlRepository = Depends(get_repository),
) -> SetPublicResponse:
    await require_superadmin(current_user=current_user)
    ok = await repo.set_job_public(job_id, payload.is_public)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found")
    return SetPublicResponse(ok=True)
