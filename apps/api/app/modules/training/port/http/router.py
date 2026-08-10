from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.shared.api.schemas import PaginatedResponse
from app.modules.auth.port.http.deps import (
    get_current_org,
    get_current_user,
)
from app.shared.api.schemas import (
    Organization,
    TrainingEvent,
    TrainingJob,
    User,
)
from app.modules.models.port.http.schemas import (
    SetPublicRequest,
    SetPublicResponse,
)
from app.modules.training.port.http.deps import (
    RepositoryDep,
    TrainingSubmissionDep,
)
from app.modules.training.port.http.schemas import (
    CreateTrainingJobRequest,
    MarkLeftResponse,
    TrainAndPredictRequest,
    TrainAndPredictResponse,
)
from app.modules.datasets.port.local import DatasetCompatibilityError
from app.modules.training.domain.submission import (
    TrainingDatasetNotFoundError,
    TrainingRuntimeUnavailableError,
    TrainingSubmissionError,
)
from app.modules.runtime.catalog import runtime_catalog
from app.modules.types.capabilities import TrainerMetadata
from app.shared.api.schemas import CancelJobResponse
from app.shared.sse.emit import emit_sse
from app.shared.sse.events import (
    SSEEvent,
    TrainingEpochEvent,
    TrainingMetricEvent,
    TrainingStatusEvent,
)

router = APIRouter(prefix="/api/v1", tags=["training"])
_SSE_EVENT_PAGE_SIZE = 200


def _training_sse_event(event: TrainingEvent) -> SSEEvent:
    event_fields = {
        "job_id": event.job_id,
        "ts": event.ts,
        "level": event.level,
        "message": event.message,
        "payload": event.payload,
    }
    if event.level == "epoch":
        return SSEEvent(TrainingEpochEvent(event_type="epoch", **event_fields))
    if event.level == "metric":
        return SSEEvent(TrainingMetricEvent(event_type="metric", **event_fields))
    return SSEEvent(TrainingStatusEvent(event_type="status", **event_fields))


@router.get("/trainers")
async def list_trainers_route(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[dict]:
    return [
        {
            "id": t.id,
            "name": t.name,
            "view_type": t.view_id,
            "trainable": True,
        }
        for t in _list_trainer_metadata()
    ]


def _list_trainer_metadata() -> list[TrainerMetadata]:
    return list(runtime_catalog.list_trainers())


@router.get("/trainers/{trainer_id}")
async def get_trainer_route(
    trainer_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    try:
        trainer_meta = runtime_catalog.get_trainer_meta(trainer_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Trainer not found") from None
    return {
        "id": trainer_meta.id,
        "name": trainer_meta.name,
        "view_type": trainer_meta.view_id,
        "trainable": True,
    }


@router.post("/training-jobs", response_model=TrainingJob)
async def create_training_job(
    payload: CreateTrainingJobRequest,
    submission: TrainingSubmissionDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TrainingJob:
    try:
        return await submission.submit_job(
            payload.to_command(org_id=org.id, created_by=current_user.id)
        )
    except TrainingDatasetNotFoundError:
        raise HTTPException(status_code=404, detail="dataset not found")
    except (DatasetCompatibilityError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TrainingRuntimeUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Failed to start training job: {exc}"
        ) from exc


@router.post("/training-jobs/train-and-predict", response_model=TrainAndPredictResponse)
async def create_train_and_predict_job(
    payload: TrainAndPredictRequest,
    submission: TrainingSubmissionDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TrainAndPredictResponse:
    try:
        result = await submission.submit_train_and_predict(
            payload.to_command(org_id=org.id, created_by=current_user.id)
        )
    except TrainingDatasetNotFoundError:
        raise HTTPException(status_code=404, detail="dataset not found")
    except DatasetCompatibilityError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TrainingRuntimeUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
    except TrainingSubmissionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return TrainAndPredictResponse(
        train_job=result.train_job,
        workflow_run_id=result.workflow_run_id,
    )


@router.get("/training-jobs", response_model=PaginatedResponse[TrainingJob])
async def list_jobs(
    repo: RepositoryDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    dataset_id: str | None = Query(default=None, description="Filter by dataset"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> PaginatedResponse[TrainingJob]:
    items, total = await repo.list_jobs_paginated(
        org_id=org.id,
        dataset_id=dataset_id,
        offset=offset,
        limit=limit,
    )
    return PaginatedResponse(items=items, total=total)


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
    submission: TrainingSubmissionDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> CancelJobResponse:
    try:
        ok = await submission.cancel_job(job_id, org_id=org.id)
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
        after_id = 0
        while True:
            if await request.is_disconnected():
                break
            while True:
                events, after_id = await repo.list_events_after(
                    job_id,
                    after_id=after_id,
                    limit=_SSE_EVENT_PAGE_SIZE,
                )
                for ev in events:
                    yield emit_sse(_training_sse_event(ev))
                if len(events) < _SSE_EVENT_PAGE_SIZE:
                    break
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
    _payload: SetPublicRequest,
    _repo: RepositoryDep,
    _current_user: User = Depends(get_current_user),
) -> SetPublicResponse:
    raise HTTPException(status_code=410, detail="Make Public is disabled")
