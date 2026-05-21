from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.modules.auth.interfaces.controllers.deps import (
    get_current_org,
    get_current_user,
)
from app.modules.schedules.api.deps import SchedulerServiceDep
from app.modules.schedules.interfaces.dtos.schemas import (
    CreateScheduleRequest,
    RunLogResponse,
    RunResponse,
    ScheduleResponse,
    UpdateScheduleRequest,
)
from app.shared.api.schemas import Organization, User

router = APIRouter(prefix="/schedules", tags=["schedules"])


def _deployment_to_schedule(raw: dict) -> ScheduleResponse:
    if "is_schedule_active" in raw and "prefect_deployment_id" in raw:
        return ScheduleResponse(
            id=raw.get("id", ""),
            name=raw.get("name", ""),
            flow_name=raw.get("flow_name", ""),
            cron=raw.get("cron"),
            parameters=raw.get("parameters", {}),
            description=raw.get("description", ""),
            is_schedule_active=raw.get("is_schedule_active", True),
            created=raw.get("created"),
            updated=raw.get("updated"),
            prefect_deployment_id=raw.get("prefect_deployment_id") or raw.get("id", ""),
        )
    schedules = raw.get("schedules", [])
    cron: str | None = None
    if schedules:
        cron = schedules[0].get("schedule", {}).get("cron")
    is_active = not raw.get("paused", False)
    return ScheduleResponse(
        id=raw.get("id", ""),
        name=raw.get("name", ""),
        flow_name=raw.get("flow_name", ""),
        cron=cron,
        parameters=raw.get("parameters", {}),
        description=raw.get("description", ""),
        is_schedule_active=is_active,
        created=raw.get("created"),
        updated=raw.get("updated"),
        prefect_deployment_id=raw.get("prefect_deployment_id") or raw.get("id", ""),
    )


def _run_to_response(raw: dict) -> RunResponse:
    return RunResponse(
        id=raw.get("id", ""),
        name=raw.get("name", ""),
        deployment_id=raw.get("deployment_id"),
        flow_name=raw.get("flow_name"),
        state_type=raw.get("state_type"),
        state_name=raw.get("state_name"),
        start_time=raw.get("start_time"),
        end_time=raw.get("end_time"),
        total_run_time=raw.get("total_run_time"),
        parameters=raw.get("parameters", {}),
    )


def _log_to_response(raw: dict) -> RunLogResponse:
    return RunLogResponse(
        id=raw.get("id"),
        flow_run_id=raw.get("flow_run_id"),
        level=raw.get("level", 0),
        timestamp=raw.get("timestamp", ""),
        message=raw.get("message", ""),
    )


@router.post("", response_model=ScheduleResponse)
async def create_schedule(
    payload: CreateScheduleRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    svc: SchedulerServiceDep,
) -> ScheduleResponse:
    raw = await svc.create_schedule(
        org_id=org.id,
        created_by=current_user.id,
        name=payload.name,
        flow_name=payload.flow_name,
        cron=payload.cron,
        parameters=payload.parameters,
        description=payload.description,
    )
    return _deployment_to_schedule(raw)


@router.get("", response_model=list[ScheduleResponse])
async def list_schedules(
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    svc: SchedulerServiceDep,
) -> list[ScheduleResponse]:
    raws = await svc.list_schedules(org_id=org.id)
    return [_deployment_to_schedule(r) for r in raws]


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    svc: SchedulerServiceDep,
) -> ScheduleResponse:
    raw = await svc.get_schedule(schedule_id, org_id=org.id)
    return _deployment_to_schedule(raw)


@router.patch("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: str,
    payload: UpdateScheduleRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    svc: SchedulerServiceDep,
) -> ScheduleResponse:
    updates = payload.model_dump(exclude_none=True)
    prefect_updates: dict = {}
    if "name" in updates:
        prefect_updates["name"] = updates["name"]
    if "description" in updates:
        prefect_updates["description"] = updates["description"]
    if "parameters" in updates:
        prefect_updates["parameters"] = updates["parameters"]
    if "is_schedule_active" in updates:
        prefect_updates["paused"] = not updates["is_schedule_active"]
    if "cron" in updates:
        prefect_updates["schedules"] = [
            {
                "schedule": {"cron": updates["cron"], "timezone": "UTC"},
                "active": True,
            }
        ]
    raw = await svc.update_schedule(schedule_id, prefect_updates)
    return _deployment_to_schedule(raw)


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    svc: SchedulerServiceDep,
) -> Response:
    await svc.delete_schedule(schedule_id)
    return Response(status_code=204)


@router.post("/{schedule_id}/run", response_model=RunResponse)
async def trigger_run(
    schedule_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    svc: SchedulerServiceDep,
) -> RunResponse:
    raw = await svc.trigger_run(schedule_id)
    return _run_to_response(raw)


@router.post("/{schedule_id}/pause", response_model=ScheduleResponse)
async def pause_schedule(
    schedule_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    svc: SchedulerServiceDep,
) -> ScheduleResponse:
    raw = await svc.pause_schedule(schedule_id)
    return _deployment_to_schedule(raw)


@router.post("/{schedule_id}/resume", response_model=ScheduleResponse)
async def resume_schedule(
    schedule_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    svc: SchedulerServiceDep,
) -> ScheduleResponse:
    raw = await svc.resume_schedule(schedule_id)
    return _deployment_to_schedule(raw)


@router.get("/{schedule_id}/runs", response_model=list[RunResponse])
async def list_runs(
    schedule_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: Annotated[User, Depends(get_current_user)] = ...,  # type: ignore[assignment]
    org: Annotated[Organization, Depends(get_current_org)] = ...,  # type: ignore[assignment]
    svc: SchedulerServiceDep = ...,  # type: ignore[assignment]
) -> list[RunResponse]:
    raws = await svc.list_runs(schedule_id, limit=limit)
    return [_run_to_response(r) for r in raws]


runs_router = APIRouter(prefix="/runs", tags=["schedules"])


@runs_router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    svc: SchedulerServiceDep,
) -> RunResponse:
    raw = await svc.get_run(run_id)
    return _run_to_response(raw)


@runs_router.get("/{run_id}/logs", response_model=list[RunLogResponse])
async def get_run_logs(
    run_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    current_user: Annotated[User, Depends(get_current_user)] = ...,  # type: ignore[assignment]
    org: Annotated[Organization, Depends(get_current_org)] = ...,  # type: ignore[assignment]
    svc: SchedulerServiceDep = ...,  # type: ignore[assignment]
) -> list[RunLogResponse]:
    raws = await svc.get_run_logs(run_id, limit=limit)
    return [_log_to_response(r) for r in raws]
