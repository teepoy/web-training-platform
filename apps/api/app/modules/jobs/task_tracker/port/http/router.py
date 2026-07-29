from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from typing import Annotated

from app.shared.api.schemas import (
    CancelJobResponse,
    PaginatedResponse,
    TaskTrackerDetailResponse,
    TaskTrackerSummaryResponse,
)
from app.shared.api.schemas import Organization, User
from app.modules.auth.port.http.deps import (
    get_current_org,
    get_current_user,
)
from app.modules.jobs.task_tracker.app.services.task_tracker import (
    TaskTrackerService,
)
from app.modules.jobs.task_tracker.port.http.deps import get_task_tracker_service
from app.shared.sse.emit import emit_sse
from app.shared.sse.events import SSEEvent, TaskTrackerStateChangeEvent

router = APIRouter(prefix="/task-tracker", tags=["task_tracker"])


@router.get(
    "/tasks",
    response_model=PaginatedResponse[TaskTrackerSummaryResponse],
)
async def list_task_tracker_tasks(
    task_tracker: Annotated[TaskTrackerService, Depends(get_task_tracker_service)],
    kind: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> PaginatedResponse[TaskTrackerSummaryResponse]:
    if kind not in (None, "training", "prediction", "schedule_run"):
        raise HTTPException(status_code=422, detail="invalid task kind")
    tasks, total = await task_tracker.list_tasks(
        org_id=org.id,
        kind=kind,
        offset=offset,
        limit=limit,
    )
    return PaginatedResponse(items=tasks, total=total)


@router.get("/tasks/{task_id}", response_model=TaskTrackerDetailResponse)
async def get_task_tracker_task(
    task_id: str,
    task_tracker: Annotated[TaskTrackerService, Depends(get_task_tracker_service)],
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TaskTrackerDetailResponse:
    detail = await task_tracker.get_task(task_id, org_id=org.id)
    if detail is None:
        raise HTTPException(status_code=404, detail="task not found")
    return detail


@router.post("/tasks/{task_id}/cancel", response_model=CancelJobResponse)
async def cancel_task_tracker_task(
    task_id: str,
    task_tracker: Annotated[TaskTrackerService, Depends(get_task_tracker_service)],
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> CancelJobResponse:
    try:
        ok = await task_tracker.cancel_task(task_id, org_id=org.id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to cancel task: {exc}")
    if not ok:
        raise HTTPException(status_code=404, detail="task not found or not cancellable")
    return CancelJobResponse(cancelled=True)


@router.get("/tasks/{task_id}/stream")
async def stream_task_tracker_task(
    task_id: str,
    request: Request,
    task_tracker: Annotated[TaskTrackerService, Depends(get_task_tracker_service)],
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
):
    if await task_tracker.get_task(task_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="task not found")

    async def event_stream():
        last_payload = ""
        while True:
            if await request.is_disconnected():
                break
            detail = await task_tracker.get_task(task_id, org_id=org.id)
            if detail is None:
                break
            payload = detail.model_dump_json()
            if payload != last_payload:
                yield emit_sse(
                    SSEEvent(
                        TaskTrackerStateChangeEvent(
                            event_type="state-change", task=detail
                        )
                    )
                )
                last_payload = payload
            status = detail.derived.display_status
            if status in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(3)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
