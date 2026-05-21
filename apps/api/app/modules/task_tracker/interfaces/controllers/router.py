import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.shared.api.schemas import (
    CancelJobResponse,
    TaskTrackerDetailResponse,
    TaskTrackerSummaryResponse,
)
from app.shared.api.schemas import Organization, User
from app.modules.auth.interfaces.controllers.deps import (
    get_current_org,
    get_current_user,
)
from app.modules.task_tracker.application.services.task_tracker import (
    TaskTrackerService,
)
from app.shared.deps import get_task_tracker  # pyright: ignore[reportMissingImports]

router = APIRouter(prefix="/api/v1", tags=["task_tracker"])


@router.get("/task-tracker/tasks", response_model=list[TaskTrackerSummaryResponse])
async def list_task_tracker_tasks(
    task_tracker: TaskTrackerService = Depends(get_task_tracker),
    kind: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[TaskTrackerSummaryResponse]:
    if kind not in (None, "training", "prediction", "schedule_run"):
        raise HTTPException(status_code=422, detail="invalid task kind")
    return await task_tracker.list_tasks(org_id=org.id, kind=kind)


@router.get("/task-tracker/tasks/{task_id}", response_model=TaskTrackerDetailResponse)
async def get_task_tracker_task(
    task_id: str,
    task_tracker: TaskTrackerService = Depends(get_task_tracker),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TaskTrackerDetailResponse:
    detail = await task_tracker.get_task(task_id, org_id=org.id)
    if detail is None:
        raise HTTPException(status_code=404, detail="task not found")
    return detail


@router.post("/task-tracker/tasks/{task_id}/cancel", response_model=CancelJobResponse)
async def cancel_task_tracker_task(
    task_id: str,
    task_tracker: TaskTrackerService = Depends(get_task_tracker),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> CancelJobResponse:
    ok = await task_tracker.cancel_task(task_id, org_id=org.id)
    if not ok:
        raise HTTPException(status_code=404, detail="task not found or not cancellable")
    return CancelJobResponse(cancelled=True)


@router.get("/task-tracker/tasks/{task_id}/stream")
async def stream_task_tracker_task(
    task_id: str,
    request: Request,
    task_tracker: TaskTrackerService = Depends(get_task_tracker),
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
            payload = json.dumps(detail.model_dump(mode="json"))
            if payload != last_payload:
                yield f"data: {payload}\n\n"
                last_payload = payload
            status = detail.derived.display_status
            if status in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(3)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
